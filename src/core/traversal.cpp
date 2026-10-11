// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Walks of the object graph that visit each object once.
//
// A PDF's objects form a graph: an object may be referenced from many places,
// and may refer back to its own ancestors. A walk that only limits its depth
// still visits a shared object once for every path that leads to it, which is
// exponential in the depth. Everything here remembers what it has visited
// instead.

#include "traversal.h"

#include "pikepdf.h"
#include "qpdf_lock.h"

#include <algorithm>
#include <cstddef>
#include <deque>
#include <string>

#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHelper.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

bool ObjectSet::add(QPDFObjectHandle h)
{
    std::lock_guard<std::mutex> guard(mutex_);
    return objects_.insert(h.getObj()).second;
}

bool ObjectSet::contains(QPDFObjectHandle h) const
{
    std::lock_guard<std::mutex> guard(mutex_);
    return objects_.count(h.getObj()) > 0;
}

void ObjectSet::discard(QPDFObjectHandle h)
{
    std::lock_guard<std::mutex> guard(mutex_);
    objects_.erase(h.getObj());
}

void ObjectSet::clear()
{
    std::lock_guard<std::mutex> guard(mutex_);
    objects_.clear();
}

size_t ObjectSet::size() const
{
    std::lock_guard<std::mutex> guard(mutex_);
    return objects_.size();
}

// The pikepdf.Object behind a Python argument, which may be an Object or a
// helper such as a Page. Returns false for anything else.
static bool object_from_python(py::handle value, QPDFObjectHandle &out)
{
    if (py::isinstance<QPDFObjectHandle>(value)) {
        out = py::cast<QPDFObjectHandle>(value);
    } else if (py::isinstance<QPDFObjectHelper>(value)) {
        out = py::cast<QPDFObjectHelper &>(value).getObjectHandle();
    } else {
        return false;
    }
    return out.isInitialized();
}

static QPDFObjectHandle require_object(py::handle value)
{
    QPDFObjectHandle h;
    if (!object_from_python(value, h))
        throw py::type_error("ObjectSet holds pikepdf.Object, or helpers such as "
                             "pikepdf.Page; other values have no identity to track");
    return h;
}

// A dictionary that is not a stream, or an uninitialized handle. Checking the
// type first keeps qpdf from warning about a malformed file, which a search
// that claims to change nothing should not do.
static QPDFObjectHandle as_dictionary(QPDFObjectHandle h)
{
    return h.isDictionary() ? h : QPDFObjectHandle();
}

// The dictionary stored under `key` of a dictionary or of a stream's
// dictionary, or an uninitialized handle.
static QPDFObjectHandle dictionary_at(QPDFObjectHandle h, std::string const &key)
{
    if (h.isStream())
        h = h.getDict();
    return h.isDictionary() ? as_dictionary(h.getKey(key)) : QPDFObjectHandle();
}

std::vector<ContentScope> ContentScopeWalk::walk(QPDFObjectHandle root, unsigned kinds)
{
    std::lock_guard<std::mutex> guard(mutex_);
    kinds_ = kinds;
    found_.clear();
    pending_.clear();
    if (!root.isDictionary() && !root.isStream())
        return {};

    // getAttribute() resolves resources a page inherits from the page tree,
    // and reads the stream dictionary when the root is a form XObject.
    bool is_form = root.isFormXObject();
    auto resources =
        as_dictionary(QPDFPageObjectHelper(root).getAttribute("/Resources", false));
    // Only a page lends its resources to the streams it uses
    page_resources_ = is_form ? QPDFObjectHandle() : resources;

    report(is_form ? scope_form : scope_page, root, resources);
    if (!is_form)
        enter_annotations(root);
    while (!pending_.empty()) {
        auto next = pending_.front();
        pending_.pop_front();
        list_resources(next);
    }
    page_resources_ = QPDFObjectHandle();
    return std::move(found_);
}

// Report a content stream with the resources it is interpreted with, unless
// that combination has been reported before, and queue the resources to be
// searched.
//
// The combination is what identifies a scope. The same stream can mean
// different things with different resources: a glyph procedure shared by two
// Type 3 fonts, or a form XObject with no resources of its own on two pages.
//
// The resources are queued even for a scope reported before, because what
// they lead to may depend on the page; list_resources() decides cheaply.
void ContentScopeWalk::report(
    content_scope_kind kind, QPDFObjectHandle content, QPDFObjectHandle resources)
{
    bool first = reported_.emplace(content.getObj(), resources.getObj()).second;
    if (first && (kinds_ & kind))
        found_.push_back({kind, content, resources});
    if (resources.isInitialized())
        pending_.push_back(resources);
}

// Record that what a resource dictionary leads to depends on the page it is
// reached from, and so does every dictionary that leads to it.
void ContentScopeWalk::mark_page_dependent(ObjectPtr resources)
{
    std::vector<ObjectPtr> todo{std::move(resources)};
    while (!todo.empty()) {
        auto dict = std::move(todo.back());
        todo.pop_back();
        if (!page_dependent_.insert(dict).second)
            continue;
        auto parents = parents_.find(dict);
        if (parents != parents_.end())
            todo.insert(todo.end(), parents->second.begin(), parents->second.end());
    }
}

// Report a content stream found in the resource dictionary being searched.
// `own` is the resource dictionary that belongs to the stream, if it has one.
//
// Files written to early versions of PDF may leave /Resources out of a form
// XObject or a Type 3 font, which then uses the resources of the page it is
// used on (ISO 32000-2, 8.10.2 and 9.6.4). What such a stream means therefore
// depends on the page, and so does what a dictionary that leads to it leads to.
void ContentScopeWalk::enter(content_scope_kind kind,
    QPDFObjectHandle content,
    QPDFObjectHandle own,
    bool may_use_page_resources)
{
    if (own.isInitialized()) {
        auto own_key = own.getObj();
        parents_[own_key].insert(listing_);
        if (page_dependent_.count(own_key))
            mark_page_dependent(listing_);
        report(kind, content, own);
    } else if (may_use_page_resources) {
        mark_page_dependent(listing_);
        report(kind, content, page_resources_);
    } else {
        report(kind, content, QPDFObjectHandle());
    }
}

void ContentScopeWalk::enter_form(content_scope_kind kind, QPDFObjectHandle form)
{
    if (form.isFormXObject())
        enter(kind, form, dictionary_at(form, "/Resources"), true);
}

void ContentScopeWalk::enter_type3_font(QPDFObjectHandle font)
{
    if (!font.isDictionary() || !font.getKey("/Subtype").isNameAndEquals("/Type3"))
        return;
    auto procs = dictionary_at(font, "/CharProcs");
    if (!procs.isInitialized())
        return;
    auto own = dictionary_at(font, "/Resources");
    for (auto const &[name, proc] : procs.ditems()) {
        if (proc.isStream())
            enter(scope_glyph, proc, own, true);
    }
}

// An annotation's appearance streams are required to have resources of their
// own, and the standard names no other source for them, so one without is
// reported with none. It is taken to be a form XObject whatever its /Subtype
// says, since nothing else can be there and files that omit the entry are
// displayed all the same.
void ContentScopeWalk::enter_appearance(QPDFObjectHandle stream)
{
    if (stream.isStream())
        report(scope_appearance, stream, dictionary_at(stream, "/Resources"));
}

void ContentScopeWalk::enter_annotations(QPDFObjectHandle page)
{
    auto annots = page.getKey("/Annots");
    if (!annots.isArray())
        return;
    for (auto const &annot : annots.aitems()) {
        // Each of /N, /R and /D is a stream, or a dictionary of streams named
        // for the states of the annotation.
        auto appearances = dictionary_at(annot, "/AP");
        if (appearances.isInitialized()) {
            for (auto const &[key, appearance] : appearances.ditems()) {
                if (appearance.isStream()) {
                    enter_appearance(appearance);
                } else if (appearance.isDictionary()) {
                    auto states = appearance; // ditems() is not const
                    for (auto const &[state, stream] : states.ditems())
                        enter_appearance(stream);
                }
            }
        }
        // The icons of a button, from which a viewer builds its appearance
        auto characteristics = dictionary_at(annot, "/MK");
        if (characteristics.isInitialized()) {
            for (auto const *key : {"/I", "/RI", "/IX"})
                enter_appearance(characteristics.getKey(key));
        }
    }
}

// Find the content streams that a resource dictionary holds.
//
// Resource dictionaries are widely shared: by many forms, and often by every
// page of a document. Each is searched once, unless what it leads to depends
// on the page, in which case it is searched once for each distinct set of
// page resources it is reached with.
void ContentScopeWalk::list_resources(QPDFObjectHandle resources)
{
    auto key = resources.getObj();
    if (listed_.count(key) && !page_dependent_.count(key))
        return;
    if (!listed_for_.emplace(key, page_resources_.getObj()).second)
        return;
    listed_.insert(key);
    listing_ = key;

    auto xobjects = dictionary_at(resources, "/XObject");
    if (xobjects.isInitialized()) {
        for (auto const &[name, xobject] : xobjects.ditems())
            enter_form(scope_form, xobject);
    }

    auto patterns = dictionary_at(resources, "/Pattern");
    if (patterns.isInitialized()) {
        for (auto const &[name, pattern] : patterns.ditems()) {
            // Only tiling patterns have content; shadings are type 2. A
            // pattern has always been required to have its own resources.
            if (!pattern.isStream())
                continue;
            auto type = pattern.getDict().getKey("/PatternType");
            if (type.isNumber() && type.getNumericValue() == 1)
                enter(scope_pattern,
                    pattern,
                    dictionary_at(pattern, "/Resources"),
                    false);
        }
    }

    auto fonts = dictionary_at(resources, "/Font");
    if (fonts.isInitialized()) {
        for (auto const &[name, font] : fonts.ditems())
            enter_type3_font(font);
    }

    auto states = dictionary_at(resources, "/ExtGState");
    if (states.isInitialized()) {
        for (auto const &[name, state] : states.ditems()) {
            // A soft mask is drawn by a transparency group, which is a form
            // XObject that no /XObject dictionary need list.
            auto mask = dictionary_at(state, "/SMask");
            if (mask.isInitialized())
                enter_form(scope_softmask, mask.getKey("/G"));
            // A graphics state may select a font: [font size]
            if (state.isDictionary()) {
                auto font = state.getKey("/Font");
                if (font.isArray() && font.getArrayNItems() >= 1)
                    enter_type3_font(font.getArrayItem(0));
            }
        }
    }
    listing_.reset();
}

// The actions that an action runs: itself, then each action reachable through
// /Next, which holds one action or an array of them. Each action appears once,
// in the order a viewer would first reach it.
static std::vector<QPDFObjectHandle> collect_action_chain(QPDFObjectHandle action)
{
    std::vector<QPDFObjectHandle> found;
    std::vector<QPDFObjectHandle> pending;
    ObjectSet seen;

    pending.push_back(action);
    while (!pending.empty()) {
        auto node = pending.back();
        pending.pop_back();
        if (!node.isDictionary() || !seen.add(node))
            continue;
        found.push_back(node);
        auto next = node.getKey("/Next");
        if (next.isArray()) {
            // Reversed, so that the first action is the next one popped
            for (int i = next.getArrayNItems() - 1; i >= 0; --i)
                pending.push_back(next.getArrayItem(i));
        } else {
            pending.push_back(next);
        }
    }
    return found;
}

// The indirect objects reachable from `roots`, each once, in the order a
// depth-first walk first meets them. An indirect integer, real, boolean or
// null is left out: pikepdf hands those to Python as plain values, so they are
// not objects a caller can examine.
static std::vector<QPDFObjectHandle> collect_reachable(
    std::vector<QPDFObjectHandle> const &roots)
{
    std::vector<QPDFObjectHandle> found;
    std::vector<QPDFObjectHandle> pending(roots.rbegin(), roots.rend());
    ObjectSet seen;

    while (!pending.empty()) {
        auto node = pending.back();
        pending.pop_back();
        auto is_container = node.isDictionary() || node.isArray() || node.isStream();
        if (node.isIndirect()) {
            if (node.isNull() || node.isBool() || node.isInteger() || node.isReal())
                continue;
            if (!seen.add(node))
                continue;
            found.push_back(node);
        } else if (is_container && !seen.add(node)) {
            // A direct container met twice is shared or part of a cycle. It
            // has nothing new below it.
            continue;
        }
        if (!is_container)
            continue;
        auto first_child = pending.size();
        if (node.isArray()) {
            for (auto const &item : node.aitems())
                pending.push_back(item);
        } else {
            auto dict = node.isStream() ? node.getDict() : node;
            for (auto const &[key, value] : dict.ditems())
                pending.push_back(value);
        }
        // Reversed, so that the first child is the next one popped
        std::reverse(
            pending.begin() + static_cast<std::ptrdiff_t>(first_child), pending.end());
    }
    return found;
}

static py::list as_python_list(std::vector<QPDFObjectHandle> const &objects)
{
    py::list result;
    for (auto const &object : objects)
        result.append(py::cast(object));
    return result;
}

void init_traversal(py::module_ &m)
{
    py::class_<ObjectSet>(m, "ObjectSet", py::type_slots(pikepdf_gc_slots))
        .def(
            "__init__",
            [](ObjectSet *self, py::object objects) {
                // Check every item before constructing: nanobind does not
                // destroy an object whose __init__ raised.
                std::vector<QPDFObjectHandle> handles;
                if (!objects.is_none()) {
                    for (auto const &item : py::cast<py::iterable>(objects))
                        handles.push_back(require_object(item));
                }
                new (self) ObjectSet();
                for (auto const &h : handles)
                    self->add(h);
            },
            py::arg("objects") = py::none())
        .def(
            "add",
            [](ObjectSet &self, py::handle obj) {
                return self.add(require_object(obj));
            },
            py::arg("obj"))
        .def(
            "discard",
            [](ObjectSet &self, py::handle obj) { self.discard(require_object(obj)); },
            py::arg("obj"))
        .def("clear", &ObjectSet::clear)
        .def("__contains__",
            [](ObjectSet &self, py::handle obj) {
                QPDFObjectHandle h;
                return object_from_python(obj, h) && self.contains(h);
            })
        .def("__len__", &ObjectSet::size)
        .def("__repr__", [](ObjectSet &self) {
            auto n = self.size();
            return "<pikepdf.ObjectSet of " + std::to_string(n) +
                   (n == 1 ? " object>" : " objects>");
        });
    m.attr("ObjectSet").attr("__hash__") = py::none();

    py::enum_<content_scope_kind>(
        m, "_ContentScopeKind", py::is_flag(), py::is_arithmetic())
        .value("page", scope_page)
        .value("form", scope_form)
        .value("appearance", scope_appearance)
        .value("pattern", scope_pattern)
        .value("glyph", scope_glyph)
        .value("softmask", scope_softmask);

    py::class_<ContentScopeWalk>(
        m, "_ContentScopeWalk", py::type_slots(pikepdf_gc_slots))
        .def(py::init<>())
        .def(
            "walk",
            [](ContentScopeWalk &self, QPDFPageObjectHelper &page, unsigned kinds) {
                auto root = page.getObjectHandle();
                QpdfLockGuard lock(root.getOwningQPDF());
                py::list result;
                for (auto const &scope : self.walk(root, kinds)) {
                    result.append(py::make_tuple(scope.kind,
                        scope.content,
                        scope.resources.isInitialized() ? py::cast(scope.resources)
                                                        : py::none()));
                }
                return result;
            },
            py::arg("page"),
            py::arg("kinds"));

    m.def("_action_chain", [](QPDFObjectHandle action) {
        QpdfLockGuard lock(action.getOwningQPDF());
        return as_python_list(collect_action_chain(action));
    });
    m.def("_reachable_objects", [](QPDF &q, py::iterable roots) {
        std::vector<QPDFObjectHandle> handles;
        for (auto const &root : roots)
            handles.push_back(py::cast<QPDFObjectHandle>(root));
        QpdfLockGuard lock(&q);
        return as_python_list(collect_reachable(handles));
    });
}

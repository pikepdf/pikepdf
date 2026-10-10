// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Walks of the object graph that visit each object once.
//
// A PDF's objects form a graph: an object may be referenced from many places,
// and may refer back to its own ancestors. A walk that only limits its depth
// still visits a shared object once for every path that leads to it, which is
// exponential in the depth. Everything here remembers what it has visited
// instead, so the work is proportional to the number of objects.

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

std::vector<QPDFObjectHandle> collect_form_xobjects(
    QPDFObjectHandle root, bool recursive, ObjectSet &seen)
{
    std::vector<QPDFObjectHandle> found;
    std::deque<QPDFObjectHandle> pending;

    // The starting point counts as visited, so a form that lists itself among
    // its own resources is not reported as nested inside itself.
    seen.add(root);
    pending.push_back(root);
    while (!pending.empty()) {
        auto node = pending.front();
        pending.pop_front();
        // getAttribute() resolves resources a page inherits from the page tree,
        // and reads the stream dictionary when the node is a form XObject.
        auto xobjects = QPDFPageObjectHelper(node)
                            .getAttribute("/Resources", false)
                            .getKeyIfDict("/XObject");
        if (!xobjects.isDictionary())
            continue;
        for (auto const &[key, value] : xobjects.ditems()) {
            if (!value.isFormXObject() || !seen.add(value))
                continue;
            found.push_back(value);
            if (recursive)
                pending.push_back(value);
        }
    }
    return found;
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
                new (self) ObjectSet();
                if (objects.is_none())
                    return;
                for (auto const &item : py::cast<py::iterable>(objects))
                    self->add(require_object(item));
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

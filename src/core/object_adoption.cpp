// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Ownership of direct objects.
//
// qpdf records an owning QPDF only on objects it parsed from a file. The
// functions here give objects built in Python the same association when they
// are inserted into a document ("adoption"), release it when they are removed
// ("disconnect"), and keep the owner pointer safe to hand back to qpdf.
// Kept separate from object.cpp because that file is already large and
// slow to compile.

#include "object.h"
#include "pikepdf.h"
#include "qpdf_lock.h"

#include <utility>
#include <vector>

#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHandle.hh>

// Maximum recursion depth when adopting a tree of direct objects. Direct
// objects form a tree, not a graph, when built through pikepdf, but a
// pathological or hand-built structure should not be able to overflow the
// stack.
static constexpr int ADOPT_MAX_DEPTH = 1000;

static bool is_scalar_object(QPDFObjectHandle const &h)
{
    switch (h.getTypeCode()) {
    case qpdf_object_type_e::ot_null:
    case qpdf_object_type_e::ot_boolean:
    case qpdf_object_type_e::ot_integer:
    case qpdf_object_type_e::ot_real:
    case qpdf_object_type_e::ot_string:
    case qpdf_object_type_e::ot_name:
    case qpdf_object_type_e::ot_operator:
    case qpdf_object_type_e::ot_inlineimage:
        return true;
    default:
        return false;
    }
}

static QPDFObjectHandle adopt_into_impl(
    QPDF *owner, QpdfEntry *entry, QPDFObjectHandle value, int depth);

// Clear an owning document's pointer from a direct object and every direct
// object below it. Depth-limited for the same reason as adoption.
static void disconnect_owner_impl(QPDFObjectHandle h, QPDF *owner, int depth)
{
    if (depth > ADOPT_MAX_DEPTH || !h.isInitialized() || h.isIndirect())
        return;
    if (h.getOwningQPDF() != owner)
        return;
    // Clearing the owner restores the object to the unowned state it had
    // before insertion. The object's value is untouched.
    h.setObjectDescription(nullptr, "");
    if (h.isDictionary()) {
        for (auto const &item : h.ditems())
            disconnect_owner_impl(item.second, owner, depth + 1);
    } else if (h.isArray()) {
        for (auto const &item : h.aitems())
            disconnect_owner_impl(item, owner, depth + 1);
    } else if (h.isStream()) {
        disconnect_owner_impl(h.getDict(), owner, depth + 1); // LCOV_EXCL_LINE
    }
}

// Release a document's claim on an object that has just been removed from that
// document's object graph, so the object can be inserted into another Pdf.
//
// Only direct objects are affected: an indirect object belongs to its document
// whether or not anything references it.
//
// Aliasing edge case: if the same direct object was reachable under two keys,
// removing either one disconnects it, even though the other still refers to
// it. The object's value is unchanged and still readable through the remaining
// reference; only the owner association is lost. Detecting the alias would
// require a full traversal of the document on every deletion.
void disconnect_from_owner(QPDF *owner, QPDFObjectHandle old)
{
    if (!owner || !old.isInitialized() || old.isIndirect())
        return;
    disconnect_owner_impl(old, owner, 0);
}

// Same, for an object being removed from `container`.
void disconnect_detached(QPDFObjectHandle &container, QPDFObjectHandle old)
{
    disconnect_from_owner(live_owner(container), old);
}

// The document that owns this object, or nullptr if it has none.
//
// qpdf records the owning QPDF as a raw pointer. Every QPDF pikepdf creates is
// in QpdfRegistry for the whole of its lifetime, so a pointer that is not in
// the registry belongs to a document that is gone. That should not happen --
// the QPDF deleter disconnects every object pikepdf adopted before the QPDF is
// destroyed -- but the registry check is cheap insurance against handing a
// stale pointer back to qpdf.
//
// Call this instead of QPDFObjectHandle::getOwningQPDF() anywhere the result is
// passed to qpdf or used to answer an ownership question. (QpdfLockGuard is
// already safe: its registry lookup returns nullptr for a dead pointer.)
QPDF *live_owner(QPDFObjectHandle &h)
{
    QPDF *owner = h.getOwningQPDF();
    if (!owner)
        return nullptr;
    if (QpdfRegistry::instance().lookup_entry(owner))
        return owner;
    return nullptr; // LCOV_EXCL_LINE
}

// Adopt the direct children of a container in place: a child that is a scalar
// is replaced by an adopted copy of itself, and a child container is tagged
// and recursed into.
static void adopt_children_impl(
    QPDF *owner, QpdfEntry *entry, QPDFObjectHandle container, int depth)
{
    if (depth > ADOPT_MAX_DEPTH)
        return;
    if (container.isDictionary()) {
        // ditems() iterates without copying the map. Only scalar children are
        // replaced, and that cannot be done while iterating, so collect the
        // replacements and apply them afterwards.
        std::vector<std::pair<std::string, QPDFObjectHandle>> replacements;
        for (auto const &[key, value] : container.ditems()) {
            auto item = value;
            auto adopted = adopt_into_impl(owner, entry, item, depth + 1);
            if (!adopted.isSameObjectAs(item))
                replacements.emplace_back(key, adopted);
        }
        for (auto const &[key, adopted] : replacements)
            container.replaceKey(key, adopted);
    } else if (container.isArray()) {
        std::vector<std::pair<int, QPDFObjectHandle>> replacements;
        int index = 0;
        for (auto const &value : container.aitems()) {
            auto item = value;
            auto adopted = adopt_into_impl(owner, entry, item, depth + 1);
            if (!adopted.isSameObjectAs(item))
                replacements.emplace_back(index, adopted);
            ++index;
        }
        for (auto const &[i, adopted] : replacements)
            container.setArrayItem(i, adopted);
    } else if (container.isStream()) {
        // Adopt the stream dictionary's children but leave the dictionary
        // itself untagged: qpdf's QPDF_Stream::setDictDescription only labels
        // a stream dictionary that has no description of its own, and a
        // description is what setObjectDescription() installs.
        adopt_children_impl(owner, entry, container.getDict(), depth + 1);
    }
}

static QPDFObjectHandle adopt_into_impl(
    QPDF *owner, QpdfEntry *entry, QPDFObjectHandle value, int depth)
{
    if (depth > ADOPT_MAX_DEPTH || !value.isInitialized())
        return value;
    // An indirect object always belongs to a document already, and an object
    // that qpdf already associates with a document (this one or another) is
    // left alone: qpdf raises ForeignObjectError for objects from another Pdf.
    if (value.isIndirect() || live_owner(value) != nullptr)
        return value;

    // An empty description leaves qpdf's error messages exactly as they were
    // for an object with no description at all; the point of the call is the
    // owning QPDF that it records.
    if (is_scalar_object(value)) {
        // Scalars are immutable in pikepdf, and a handle such as a Name held
        // in a module-level constant is often inserted into several documents.
        // Adopt a copy so the caller's object stays unowned and reusable.
        auto copy = value.shallowCopy();
        copy.setObjectDescription(owner, "");
        if (entry)
            entry->record_adopted(copy.getObj());
        return copy;
    }

    // Containers are adopted in place: pikepdf callers expect a dictionary or
    // array they assigned into a Pdf to stay aliased with the document.
    value.setObjectDescription(owner, "");
    if (entry)
        entry->record_adopted(value.getObj());
    adopt_children_impl(owner, entry, value, depth);
    return value;
}

// Give a direct object, and every direct object below it, the same owning
// document as the container it is about to be inserted into, and return the
// handle that should actually be inserted.
//
// qpdf only associates a document with objects that it read from that
// document, so an object built in Python (the 42 in ``pdf.Root.Count = 42``,
// or a ``Dictionary(...)`` assigned into a Pdf) would otherwise belong to no
// document at all. Adoption at insertion time is what lets per-document
// settings, such as Pdf.conversion_mode, apply to objects created in the
// current session, and it matches what qpdf does for objects parsed from a
// file.
QPDFObjectHandle adopt_into(QPDF *owner, QPDFObjectHandle value)
{
    if (!owner)
        return value;
    // One registry lookup for the whole subtree.
    auto *entry = QpdfRegistry::instance().lookup_entry(owner);
    return adopt_into_impl(owner, entry, value, 0);
}

// Adopt the direct children of a container that already has an owner, such as
// an object that was just made indirect or copied from another document.
void adopt_children_into(QPDF *owner, QPDFObjectHandle container)
{
    if (!owner)
        return;
    auto *entry = QpdfRegistry::instance().lookup_entry(owner);
    adopt_children_impl(owner, entry, container, 0);
}

// Finish promoting a direct object to an indirect object of `owner`.
//
// pikepdf tags an adopted direct object with an empty description, because a
// direct object has no obj/gen to name it with. Once the object is indirect it
// does have one, but qpdf only falls back to its "object N 0" label when the
// object has no description at all, so the empty tag would silently suppress
// the label in every warning about the object. Reinstating qpdf's own template
// restores it. ($OG is expanded to the obj/gen by QPDFObject::getDescription.)
static void adopt_made_indirect(QPDF *owner, QPDFObjectHandle indirect)
{
    if (!owner)
        return; // LCOV_EXCL_LINE
    indirect.setObjectDescription(owner, "object $OG");
    adopt_children_into(owner, indirect);
}

// Make a direct object indirect in owner, and adopt it.
//
// qpdf files the handle's shared object under a new object number, which
// turns every handle sharing it indirect, including the caller's. For a
// scalar that would break hashing, since only direct scalars are hashable,
// and would tie a reusable constant such as a module-level Name to one
// document. So, as with adoption, a scalar is made indirect from a copy.
// Containers are made indirect in place, since callers expect the object they
// passed to stay aliased with the document.
QPDFObjectHandle make_direct_indirect(QPDF *owner, QPDFObjectHandle direct)
{
    auto target = is_scalar_object(direct) ? direct.shallowCopy() : direct;
    auto indirect = owner->makeIndirectObject(target);
    adopt_made_indirect(owner, indirect);
    return indirect;
}

// Raise ForeignObjectError for a direct object that belongs to another Pdf.
//
// qpdf itself only guards indirect objects; a direct object carries its owner
// in a description, and silently retagging it would detach it from the
// document that still references it.
void refuse_to_steal(QPDFObjectHandle &h, QPDF *target)
{
    if (h.isIndirect())
        return;
    QPDF *owner = live_owner(h);
    if (owner && owner != target)
        throw_foreign_object_error(
            "This object belongs to another Pdf. Remove it from that document "
            "first, or make it indirect there and use Pdf.copy_foreign().");
}

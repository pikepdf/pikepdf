// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "pikepdf.h"

#include <memory>
#include <mutex>
#include <unordered_set>
#include <vector>

#include <qpdf/QPDFObjectHandle.hh>

// The set of objects a walk of the object graph has already visited.
//
// Objects are told apart by identity, the same test as isSameObjectAs(), rather
// than by object and generation number. Every handle to an indirect object
// shares one underlying QPDFObject, so identity covers what a set of obj/gen
// pairs would, and it also tells direct objects apart (they all report 0 0)
// and objects of different documents apart (whose numbers coincide).
//
// The set holds a reference to each object so that an address is never reused
// for a different object while the set is alive.
class ObjectSet {
public:
    ObjectSet() = default;
    ObjectSet(const ObjectSet &) = delete;
    ObjectSet &operator=(const ObjectSet &) = delete;

    // Returns true if the object was not in the set before this call.
    bool add(QPDFObjectHandle h);
    bool contains(QPDFObjectHandle h) const;
    void discard(QPDFObjectHandle h);
    void clear();
    size_t size() const;

private:
    // A real mutex, not the per-QPDF lock: a set may hold objects of several
    // documents, or of none.
    mutable std::mutex mutex_;
    std::unordered_set<std::shared_ptr<QPDFObject>> objects_;
};

// The form XObjects in the /Resources of a page or form XObject, each once.
// Forms already in `seen` are neither returned nor entered.
std::vector<QPDFObjectHandle> collect_form_xobjects(
    QPDFObjectHandle root, bool recursive, ObjectSet &seen);

void init_traversal(py::module_ &m);

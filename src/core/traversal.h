// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "pikepdf.h"

#include <memory>
#include <mutex>
#include <set>
#include <unordered_set>
#include <utility>
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

    // Remember that `content` was interpreted with `resources`, for a content
    // stream that has no resources of its own and so means something different
    // in each context that uses it. Either handle may be uninitialized.
    // Returns true the first time the combination is seen. These combinations
    // are not members of the set: they do not count towards size().
    bool add_pair(QPDFObjectHandle content, QPDFObjectHandle resources);

private:
    // A real mutex, not the per-QPDF lock: a set may hold objects of several
    // documents, or of none.
    mutable std::mutex mutex_;
    std::unordered_set<std::shared_ptr<QPDFObject>> objects_;
    std::set<std::pair<std::shared_ptr<QPDFObject>, std::shared_ptr<QPDFObject>>>
        pairs_;
};

// The form XObjects in the /Resources of a page or form XObject, each once.
// Forms already in `seen` are neither returned nor entered.
std::vector<QPDFObjectHandle> collect_form_xobjects(
    QPDFObjectHandle root, bool recursive, ObjectSet &seen);

// The kinds of content stream that collect_content_scopes() reports, as bits
// of a mask. pikepdf/_content_scopes.py holds the same values.
enum content_scope_kind : unsigned {
    scope_page = 1,
    scope_form = 2,
    scope_appearance = 4,
    scope_pattern = 8,
    scope_glyph = 16,
    scope_softmask = 32,
};

// A content stream and the resources it is interpreted with.
struct ContentScope {
    content_scope_kind kind;
    QPDFObjectHandle content;
    QPDFObjectHandle resources; // uninitialized if there are none
};

// The content streams of a page or form XObject and everything they can draw,
// each once for each resource dictionary it is interpreted with. A kind that
// is not in `kinds` is neither reported nor searched.
std::vector<ContentScope> collect_content_scopes(
    QPDFObjectHandle root, unsigned kinds, ObjectSet &seen);

void init_traversal(py::module_ &m);

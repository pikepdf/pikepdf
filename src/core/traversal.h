// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "pikepdf.h"

#include <deque>
#include <memory>
#include <mutex>
#include <set>
#include <unordered_map>
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

private:
    // A real mutex, not the per-QPDF lock: a set may hold objects of several
    // documents, or of none.
    mutable std::mutex mutex_;
    std::unordered_set<std::shared_ptr<QPDFObject>> objects_;
    std::set<std::pair<std::shared_ptr<QPDFObject>, std::shared_ptr<QPDFObject>>>
        pairs_;
};

// The kinds of content stream that ContentScopeWalk reports, as bits of a
// mask. Bound as pikepdf._core._ContentScopeKind, whose member names are the
// names that Python callers use for the kinds.
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

// Finds the content streams a page can draw: the page itself, and the form
// XObjects, annotation appearance streams, tiling patterns, Type 3 glyph
// procedures and soft mask groups it uses, however they are nested.
//
// One walk may be given many pages. It remembers what it has reported and
// which resource dictionaries it has searched, so that what the pages share
// is reported and searched once, and the work is proportional to the size of
// what is reachable rather than to the number of pages times that size.
//
// The walk keeps a reference to everything it has seen, since Python may
// change the document between one page and the next.
class ContentScopeWalk {
public:
    ContentScopeWalk() = default;
    ContentScopeWalk(const ContentScopeWalk &) = delete;
    ContentScopeWalk &operator=(const ContentScopeWalk &) = delete;

    // The scopes of `root`, a page or form XObject, that have not been
    // reported before. Everything is searched whatever `kinds` is; only the
    // kinds in the mask are returned.
    std::vector<ContentScope> walk(QPDFObjectHandle root, unsigned kinds);

private:
    using ObjectPtr = std::shared_ptr<QPDFObject>;

    void report(
        content_scope_kind kind, QPDFObjectHandle content, QPDFObjectHandle resources);
    void mark_page_dependent(ObjectPtr resources);
    void enter(content_scope_kind kind,
        QPDFObjectHandle content,
        QPDFObjectHandle own,
        bool may_use_page_resources);
    void enter_form(content_scope_kind kind, QPDFObjectHandle form);
    void enter_type3_font(QPDFObjectHandle font);
    void enter_appearance(QPDFObjectHandle stream);
    void enter_annotations(QPDFObjectHandle page);
    void list_resources(QPDFObjectHandle resources);

    std::mutex mutex_;
    // (content, resources) of each scope reported
    std::set<std::pair<ObjectPtr, ObjectPtr>> reported_;
    // Resource dictionaries searched, and (dictionary, page resources) for
    // each search
    std::unordered_set<ObjectPtr> listed_;
    std::set<std::pair<ObjectPtr, ObjectPtr>> listed_for_;
    // Resource dictionaries that lead to a stream which uses the page's
    // resources, and for each dictionary, the dictionaries that lead to it
    std::unordered_set<ObjectPtr> page_dependent_;
    std::unordered_map<ObjectPtr, std::unordered_set<ObjectPtr>> parents_;

    // State of the walk in progress
    unsigned kinds_{0};
    QPDFObjectHandle page_resources_;
    ObjectPtr listing_;
    std::deque<QPDFObjectHandle> pending_;
    std::vector<ContentScope> found_;
};

void init_traversal(py::module_ &m);

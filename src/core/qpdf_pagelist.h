// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "locked_bindings.h"
#include "pikepdf.h"

#include <atomic>
#include <memory>
#include <vector>

#include <qpdf/QPDFPageDocumentHelper.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

void init_pagelist(py::module_ &m);

class PageList { // LCOV_EXCL_LINE
public:
    PageList(std::shared_ptr<QPDF> q) : qpdf(q), doc(*qpdf) {};

    QPDFPageObjectHelper get_page(size_t index);
    py::list get_pages(py::slice slice);
    void set_page(size_t index, QPDFPageObjectHelper page);
    void set_page(size_t index, py::object obj);
    void set_pages_from_iterable(py::slice slice, py::iterable other);
    void set_pages(py::slice slice, std::vector<QPDFPageObjectHelper> const &pages);
    void delete_page(size_t index);
    void delete_pages_from_iterable(py::slice slice);
    size_t count();
    void adopt_page_at(size_t index);
    void insert_page(size_t index, QPDFPageObjectHelper page);
    void append_page(QPDFPageObjectHelper page);

public:
    std::shared_ptr<QPDF> qpdf;
    QPDFPageDocumentHelper doc;

private:
    std::vector<QPDFPageObjectHelper> get_page_objs_impl(py::slice slice);
};

// Iterates over the pages a PageList had when the iterator was created.
//
// The pages are copied out of the Pdf, under its lock, when the iterator is
// constructed. After that the list is never changed and the position is
// atomic, so advancing the iterator reads no Pdf and needs no lock, even when
// threads share one iterator. The iterator shares ownership of the Pdf, as the
// PageList does, so that the pages it has yet to yield keep their owner.
class PageListIterator { // LCOV_EXCL_LINE
public:
    PageListIterator(PageList &pl, size_t index)
        : qpdf_(pl.qpdf), index_(index), pages_(pl.doc.getAllPages()) {};
    PageListIterator(PageListIterator const &other)
        : qpdf_(other.qpdf_), index_(other.index_.load()), pages_(other.pages_) {};
    QPDFPageObjectHelper next();

private:
    std::shared_ptr<QPDF> qpdf_;
    std::atomic<size_t> index_;
    std::vector<QPDFPageObjectHelper> pages_;
};

template <>
struct LockOwner<PageList> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(PageList const &pl) { return pl.qpdf.get(); }
};

// See the class: an iterator holds a copy of the page list, not Pdf state.
template <>
struct LockOwner<PageListIterator> : NoLock {};

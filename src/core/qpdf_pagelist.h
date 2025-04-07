// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "pikepdf.h"

#include <pybind11/stl.h>

#include <qpdf/QPDFPageObjectHelper.hh>
#include <qpdf/QPDFPageDocumentHelper.hh>

void init_pagelist(py::module_ &m);

class PageList { // LCOV_EXCL_LINE
public:
    PageList(std::shared_ptr<QPDF> q) : qpdf(q), doc(*qpdf) {};

    QPDFPageObjectHelper get_page(py::size_t index);
    py::list get_pages(py::slice slice);
    void set_page(py::size_t index, QPDFPageObjectHelper page);
    void set_page(py::size_t index, py::object obj);
    void set_pages_from_iterable(py::slice slice, py::iterable other);
    void delete_page(py::size_t index);
    void delete_pages_from_iterable(py::slice slice);
    py::size_t count();
    void insert_page(py::size_t index, QPDFPageObjectHelper page);
    void append_page(QPDFPageObjectHelper page);

public:
    std::shared_ptr<QPDF> qpdf;
    QPDFPageDocumentHelper doc;

private:
    std::vector<QPDFPageObjectHelper> get_page_objs_impl(py::slice slice);
};

class PageListIterator { // LCOV_EXCL_LINE
public:
    PageListIterator(PageList &pl, size_t index)
        : pl(pl), index(index), pages(pl.doc.getAllPages()) {};
    QPDFPageObjectHelper next();

private:
    PageList &pl;
    size_t index;
    std::vector<QPDFPageObjectHelper> pages;
};
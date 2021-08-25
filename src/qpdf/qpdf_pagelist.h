/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#pragma once

#include "pikepdf.h"

#include <pybind11/stl.h>

#include <qpdf/QPDFPageObjectHelper.hh>

void init_pagelist(py::module_ &m);

class PageList {
public:
    PageList(std::shared_ptr<QPDF> q, py::size_t iterpos = 0)
        : iterpos(iterpos), qpdf(q){};

    QPDFObjectHandle get_page_obj(py::size_t index) const;
    QPDFPageObjectHelper get_page(py::size_t index) const;
    py::list get_pages(py::slice slice) const;
    void set_page(py::size_t index, py::object page);
    void set_pages_from_iterable(py::slice slice, py::iterable other);
    void delete_page(py::size_t index);
    void delete_pages_from_iterable(py::slice slice);
    py::size_t count() const;
    void insert_page(py::size_t index, py::handle obj);
    void insert_page(py::size_t index, QPDFPageObjectHelper page);

public:
    py::size_t iterpos;
    std::shared_ptr<QPDF> qpdf;

private:
    std::vector<QPDFObjectHandle> get_page_objs_impl(py::slice slice) const;
};

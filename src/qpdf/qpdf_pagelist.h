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


void init_pagelist(py::module &m);

class PageList {
public:
    PageList(std::shared_ptr<QPDF> q, size_t iterpos = 0) : iterpos(iterpos), qpdf(q) {};

    QPDFObjectHandle get_page(size_t index) const;
    py::list get_pages(py::slice slice) const;
    void set_page(size_t index, py::object page);
    void set_pages_from_iterable(py::slice slice, py::iterable other);
    void delete_page(size_t index);
    void delete_pages_from_iterable(py::slice slice);
    size_t count() const;
    void insert_page(size_t index, py::handle obj);
    void insert_page(size_t index, QPDFObjectHandle page);
public:
    size_t iterpos;
    std::shared_ptr<QPDF> qpdf;

private:
    std::vector<QPDFObjectHandle> get_pages_impl(py::slice slice) const;
};

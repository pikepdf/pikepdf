/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include "pikepdf.h"
#include "qpdf_pagelist.h"

static void assert_pyobject_is_page(py::handle obj)
{
    QPDFObjectHandle h;
    try {
        h = obj.cast<QPDFObjectHandle>();
    } catch (const py::cast_error&) {
        throw py::type_error("only pikepdf pages can be assigned to a page list");
    }
    if (!h.isPageObject()) {
        throw py::type_error("only pages can be assigned to a page list");
    }
}

size_t uindex_from_index(PageList &pl, ssize_t index)
{
    if (index < 0)
        index += pl.count();
    if (index < 0) // Still
        throw py::index_error("Accessing nonexistent PDF page number");
    size_t uindex = index;
    return uindex;
}

QPDFObjectHandle PageList::get_page(size_t index) const
{
    auto pages = this->qpdf->getAllPages();
    if (index < 0)
        index += pages.size();
    if (index < 0) // Still
        throw py::index_error("Accessing nonexistent PDF page number");
    size_t uindex = index;
    if (uindex < pages.size())
        return pages.at(uindex);
    throw py::index_error("Accessing nonexistent PDF page number");
}

std::vector<QPDFObjectHandle> PageList::get_pages_impl(py::slice slice) const
{
    size_t start, stop, step, slicelength;
    if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
        throw py::error_already_set();
    std::vector<QPDFObjectHandle> result;
    for (size_t i = 0; i < slicelength; ++i) {
        QPDFObjectHandle oh = this->get_page(start);
        result.push_back(oh);
        start += step;
    }
    return result;
}

py::list PageList::get_pages(py::slice slice) const
{
    return py::cast(this->get_pages_impl(slice));
}

void PageList::set_page(size_t index, py::object page)
{
    this->insert_page(index, page);
    if (index != this->count()) {
        this->delete_page(index + 1);
    }
}

void PageList::set_pages_from_iterable(py::slice slice, py::iterable other)
{
    size_t start, stop, step, slicelength;
    if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
        throw py::error_already_set();
    py::list results;
    py::iterator it = other.attr("__iter__")();

    // Unpack list into iterable, check that each object is a page but
    // don't save the handles yet
    for(; it != py::iterator::sentinel(); ++it) {
        assert_pyobject_is_page(*it);
        results.append(*it);
    }

    if (step != 1) {
        // For an extended slice we must be replace an equal number of pages
        if (results.size() != slicelength) {
            throw py::value_error(
                std::string("attempt to assign sequence of length ") +
                std::to_string(results.size()) +
                std::string(" to extended slice of size ") +
                std::to_string(slicelength)
            );
        }
        for (size_t i = 0; i < slicelength; ++i) {
            this->set_page(start + (i * step), results[i]);
        }
    } else {
        // For simple slices, we can replace differing sizes
        // meaning results.size() could be slicelength, or not
        // so insert all pages first (to ensure nothing is freed yet)
        // and then delete all pages we no longer need

        // Insert first to ensure we don't delete any pages we will need
        for (size_t i = 0; i < results.size(); ++i) {
            this->insert_page(start + i, results[i]);
        }

        size_t del_start = start + results.size();
        for (size_t i = 0; i < slicelength; ++i) {
            this->delete_page(del_start);
        }
    }
}

void PageList::delete_page(size_t index)
{
    auto page = this->get_page(index);
    /*
    // Need a dec_ref to match the inc_ref in insert_page, but it's unclear
    // how to do that. The item will be set the current QPDF always.
    // Accessing data from another PDF seems to involve some pipeline
    // magic in QPDF around libqpdf/QPDFWriter.cc:1614
    if (original page owner != &this->getQPDF()) {
        // If we are removing a page not originally owned by our QPDF,
        // remove the reference count we put it in insert_page()
        py::object pyqpdf = py::cast(page_owner);
        pyqpdf.dec_ref();
    }
    */
    this->qpdf->removePage(page);
}

void PageList::delete_pages_from_iterable(py::slice slice)
{
    // See above: need a way to dec_ref pages with another owner
    // Get handles for all pages, then remove them, since page numbers shift
    // after delete
    auto kill_list = this->get_pages_impl(slice);
    for (auto page : kill_list) {
        this->qpdf->removePage(page);
    }
}

size_t PageList::count() const
{
    return this->qpdf->getAllPages().size();
}

void PageList::insert_page(size_t index, py::handle obj)
{
    QPDFObjectHandle page;
    try {
        page = obj.cast<QPDFObjectHandle>();
    } catch (const py::cast_error&) {
        throw py::type_error("only pages can be inserted");
    }
    if (!page.isPageObject())
        throw py::type_error("only pages can be inserted");

    this->insert_page(index, page);
}

void PageList::insert_page(size_t index, QPDFObjectHandle page)
{
    // Find out who owns us
    QPDF *page_owner = page.getOwningQPDF();

    if (page_owner == this->qpdf.get()) {
        // qpdf does not accept duplicating pages within the same file,
        // so manually create a copy
        page = this->qpdf->makeIndirectObject(page);
    } else {
        // libqpdf does not transfer a page's contents to the new QPDF.
        // Instead WHEN ASKED TO WRITE it will go back and get the data
        // from objecthandle->getOwningQPDF(). Therefore we must ensure
        // our previous owner is kept alive.
#if 1
        auto tinfo = py::detail::get_type_info(typeid(QPDF));
        py::handle pyqpdf = py::detail::get_object_handle(page_owner, tinfo);
        py::handle pypage = py::cast(page);
        py::detail::keep_alive_impl(pypage, pyqpdf);
#else
        // MSVC++ complains about the symbol
        // QPDF::Members::~Members() not being exported when this version
        // is used, but it works for GCC and Clang.
        py::handle pyqpdf = py::cast(page_owner);
        py::handle pypage = py::cast(page);
        py::detail::keep_alive_impl(pypage, pyqpdf);
#endif
    }
    if (index != this->count()) {
        QPDFObjectHandle refpage = this->get_page(index);
        this->qpdf->addPageAt(page, true, refpage);
    } else {
        this->qpdf->addPage(page, false);
    }
}


void init_pagelist(py::module &m)
{
    py::class_<PageList>(m, "PageList")
        .def("__getitem__",
            [](PageList &pl, ssize_t index) {
                size_t uindex = uindex_from_index(pl, index);
                return pl.get_page(uindex);
            }
        )
        .def("__getitem__", &PageList::get_pages)
        .def("__setitem__",
            [](PageList &pl, ssize_t index, py::object page) {
                size_t uindex = uindex_from_index(pl, index);
                pl.set_page(uindex, page);
            }
        )
        .def("__setitem__", &PageList::set_pages_from_iterable)
        .def("__delitem__",
            [](PageList &pl, ssize_t index) {
                size_t uindex = uindex_from_index(pl, index);
                pl.delete_page(uindex);
            }
        )
        .def("__delitem__", &PageList::delete_pages_from_iterable)
        .def("__len__", &PageList::count)
        .def("p",
            [](PageList &pl, size_t index) {
                if (index == 0) // Indexing past end is checked in .get_page
                    throw py::index_error("page access out of range in 1-based indexing");
                return pl.get_page(index - 1);
            },
            "convenience - look up page number in ordinal numbering, .p(1) is first page"
        )
        .def("__iter__",
            [](PageList &pl) {
                return PageList(pl.qpdf, 0);
            }
        )
        .def("__next__",
            [](PageList &pl) {
                if (pl.iterpos < pl.count())
                    return pl.get_page(pl.iterpos++);
                throw py::stop_iteration();
            }
        )
        .def("insert",
            [](PageList &pl, ssize_t index, py::object obj) {
                size_t uindex = uindex_from_index(pl, index);
                pl.insert_page(uindex, obj);
            }, py::keep_alive<1, 3>()
        )
        .def("reverse",
            [](PageList &pl) {
                py::slice ordinary_indices(0, pl.count(), 1);
                py::int_ step(-1);
                py::slice reversed = py::reinterpret_steal<py::slice>(
                    PySlice_New(Py_None, Py_None, step.ptr()));
                py::list reversed_pages = pl.get_pages(reversed);
                pl.set_pages_from_iterable(ordinary_indices, reversed_pages);
            }
        )
        .def("append",
            [](PageList &pl, py::object page) {
                pl.insert_page(pl.count(), page);
            },
            py::keep_alive<1, 2>()
        )
        .def("extend",
            [](PageList &pl, PageList &other) {
                size_t other_count = other.count();
                for (size_t i = 0; i < other_count; i++) {
                    if (other_count != other.count())
                        throw py::value_error("source page list modified during iteration");
                    pl.insert_page(pl.count(), other.get_page(i));
                }
            },
            py::keep_alive<1, 2>()
        )
        .def("extend",
            [](PageList &pl, py::iterable iterable) {
                py::iterator it = iterable.attr("__iter__")();
                while (it != py::iterator::sentinel()) {
                    assert_pyobject_is_page(*it);
                    pl.insert_page(pl.count(), *it);
                    ++it;
                }
            },
            py::keep_alive<1, 2>()
        );
}

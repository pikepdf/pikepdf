/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include "pikepdf.h"
#include "qpdf_pagelist.h"

#include <qpdf/QPDFPageObjectHelper.hh>
#include <qpdf/QPDFPageDocumentHelper.hh>
#include <qpdf/QPDFPageLabelDocumentHelper.hh>

static void assert_pyobject_is_page_helper(py::handle obj)
{
    try {
        auto poh = obj.cast<QPDFPageObjectHelper>();
    } catch (const py::cast_error &) {
        throw py::type_error(
            std::string(
                "only pikepdf pages can be assigned to a page list; tried to assign ") +
            std::string(py::repr(py::type::of(obj))));
    }
}

py::size_t uindex_from_index(PageList &pl, py::ssize_t index)
{
    if (index < 0)
        index += pl.count();
    if (index < 0) // Still
        throw py::index_error("Accessing nonexistent PDF page number");
    py::size_t uindex = index;
    return uindex;
}

QPDFObjectHandle PageList::get_page_obj(py::size_t index) const
{
    auto pages = this->qpdf->getAllPages();
    if (index < pages.size())
        return pages.at(index);
    throw py::index_error("Accessing nonexistent PDF page number");
}

QPDFPageObjectHelper PageList::get_page(py::size_t index) const
{
    return QPDFPageObjectHelper(this->get_page_obj(index));
}

std::vector<QPDFObjectHandle> PageList::get_page_objs_impl(py::slice slice) const
{
    py::size_t start, stop, step, slicelength;
    if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
        throw py::error_already_set(); // LCOV_EXCL_LINE
    std::vector<QPDFObjectHandle> result;
    for (py::size_t i = 0; i < slicelength; ++i) {
        auto oh = this->get_page_obj(start);
        result.push_back(oh);
        start += step;
    }
    return result;
}

py::list PageList::get_pages(py::slice slice) const
{
    auto page_objs = this->get_page_objs_impl(slice);
    py::list result;
    for (auto &page_obj : page_objs) {
        result.append(py::cast(QPDFPageObjectHelper(page_obj)));
    }
    return result;
}

void PageList::set_page(py::size_t index, py::object page)
{
    this->insert_page(index, page);
    if (index != this->count()) {
        this->delete_page(index + 1);
    }
}

void PageList::set_pages_from_iterable(py::slice slice, py::iterable other)
{
    py::size_t start, stop, step, slicelength;
    if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
        throw py::error_already_set(); // LCOV_EXCL_LINE
    py::list results;
    py::iterator it = other.attr("__iter__")();

    // Unpack list into iterable, check that each object is a page but
    // don't save the handles yet
    for (; it != py::iterator::sentinel(); ++it) {
        // assert_pyobject_is_page_obj(*it);
        assert_pyobject_is_page_helper(*it);
        results.append(*it);
    }

    if (step != 1) {
        // For an extended slice we must be replace an equal number of pages
        if (results.size() != slicelength) {
            throw py::value_error(std::string("attempt to assign sequence of length ") +
                                  std::to_string(results.size()) +
                                  std::string(" to extended slice of size ") +
                                  std::to_string(slicelength));
        }
        for (py::size_t i = 0; i < slicelength; ++i) {
            this->set_page(start + (i * step), results[i]);
        }
    } else {
        // For simple slices, we can replace differing sizes
        // meaning results.size() could be slicelength, or not
        // so insert all pages first (to ensure nothing is freed yet)
        // and then delete all pages we no longer need

        // Insert first to ensure we don't delete any pages we will need
        for (py::size_t i = 0; i < results.size(); ++i) {
            this->insert_page(start + i, results[i]);
        }

        py::size_t del_start = start + results.size();
        for (py::size_t i = 0; i < slicelength; ++i) {
            this->delete_page(del_start);
        }
    }
}

void PageList::delete_page(py::size_t index)
{
    auto page = this->get_page_obj(index);
    this->qpdf->removePage(page);
}

void PageList::delete_pages_from_iterable(py::slice slice)
{
    // See above: need a way to dec_ref pages with another owner
    // Get handles for all pages, then remove them, since page numbers shift
    // after delete
    auto kill_list = this->get_page_objs_impl(slice);
    for (auto page : kill_list) {
        this->qpdf->removePage(page);
    }
}

py::size_t PageList::count() const { return this->qpdf->getAllPages().size(); }

void PageList::insert_page(py::size_t index, py::handle obj)
{
    try {
        auto poh = obj.cast<QPDFPageObjectHelper>();
        this->insert_page(index, poh);
        return;
    } catch (py::cast_error &) {
        try {
            auto oh = obj.cast<QPDFObjectHandle>();
            this->insert_page(index, QPDFPageObjectHelper(oh));
        } catch (py::cast_error &) {
            throw py::type_error("tried to insert object which is neither pikepdf.Page "
                                 "nor pikepdf.Dictionary with type page");
        }
        return;
    }

    throw py::type_error("only pages can be inserted to a page list");
}

void PageList::insert_page(py::size_t index, QPDFPageObjectHelper poh)
{
    // Find out who owns us
    QPDF *handle_owner = poh.getObjectHandle().getOwningQPDF();
    QPDFObjectHandle page_obj;
    bool copied = false;

    if (handle_owner == this->qpdf.get() || !handle_owner) {
        // qpdf does not accept duplicating pages within the same file,
        // so manually create a copy
        page_obj = this->qpdf->makeIndirectObject(poh.getObjectHandle().shallowCopy());
        copied   = true;
    } else {
        page_obj = poh.getObjectHandle();
    }

    auto doc  = QPDFPageDocumentHelper(*this->qpdf);
    auto page = QPDFPageObjectHelper(page_obj);

    try {
        if (!page_obj.isPageObject()) {
            throw py::type_error(std::string("only pages can be inserted - you tried "
                                             "to insert this as a page: ") +
                                 objecthandle_repr(page_obj));
        }

        if (index != this->count()) {
            auto refpage = this->get_page(index);
            doc.addPageAt(page, true, refpage);
        } else {
            doc.addPage(page, false);
        }
    } catch (const std::runtime_error &e) {
        if (copied) {
            // If we created a new object to hold the page, and failed, delete
            // the object we created.
            this->qpdf->replaceObject(
                page_obj.getObjGen(), QPDFObjectHandle::newNull());
        }
        throw;
    }
}

QPDFPageObjectHelper from_objgen(QPDF &q, QPDFObjGen og)
{
    auto h = q.getObjectByObjGen(og);
    if (!h.isPageObject())
        throw py::value_error("Object is not a page");
    return QPDFPageObjectHelper(h);
}

void init_pagelist(py::module_ &m)
{
    py::class_<PageList>(m, "PageList")
        .def("__getitem__",
            [](PageList &pl, py::ssize_t index) {
                auto uindex = uindex_from_index(pl, index);
                return pl.get_page(uindex);
            })
        .def("__getitem__", &PageList::get_pages)
        .def("__setitem__",
            [](PageList &pl, py::ssize_t index, py::object page) {
                auto uindex = uindex_from_index(pl, index);
                pl.set_page(uindex, page);
            })
        .def("__setitem__", &PageList::set_pages_from_iterable)
        .def("__delitem__",
            [](PageList &pl, py::ssize_t index) {
                auto uindex = uindex_from_index(pl, index);
                pl.delete_page(uindex);
            })
        .def("__delitem__", &PageList::delete_pages_from_iterable)
        .def("__len__", &PageList::count)
        .def(
            "p",
            [](PageList &pl, py::ssize_t pnum) {
                if (pnum <= 0) // Indexing past end is checked in .get_page
                    throw py::index_error(
                        "page access out of range in 1-based indexing");
                return pl.get_page(pnum - 1);
            },
            "Convenience - look up page number in ordinal numbering, ``.p(1)`` is "
            "first page",
            py::arg("pnum"))
        .def("__iter__", [](PageList &pl) { return PageList(pl.qpdf, 0); })
        .def("__next__",
            [](PageList &pl) {
                if (pl.iterpos < pl.count())
                    return pl.get_page(pl.iterpos++);
                throw py::stop_iteration();
            })
        .def(
            "insert",
            [](PageList &pl, py::ssize_t index, py::object obj) {
                auto uindex = uindex_from_index(pl, index);
                pl.insert_page(uindex, obj);
            },
            py::keep_alive<1, 3>(),
            R"~~~(
            Insert a page at the specified location.

            Args:
                index (int): location at which to insert page, 0-based indexing
                obj (pikepdf.Object): page object to insert
            )~~~",
            py::arg("index"),
            py::arg("obj"))
        .def(
            "reverse",
            [](PageList &pl) {
                py::slice ordinary_indices(0, pl.count(), 1);
                py::int_ step(-1);
                py::slice reversed = py::reinterpret_steal<py::slice>(
                    PySlice_New(Py_None, Py_None, step.ptr()));
                py::list reversed_pages = pl.get_pages(reversed);
                pl.set_pages_from_iterable(ordinary_indices, reversed_pages);
            },
            "Reverse the order of pages.")
        .def(
            "append",
            [](PageList &pl, py::object page) { pl.insert_page(pl.count(), page); },
            py::keep_alive<1, 2>(),
            "Add another page to the end.",
            py::arg("page"))
        .def(
            "extend",
            [](PageList &pl, PageList &other) {
                auto other_count = other.count();
                for (decltype(other_count) i = 0; i < other_count; i++) {
                    if (other_count != other.count())
                        throw py::value_error(
                            "source page list modified during iteration");
                    pl.insert_page(pl.count(), other.get_page_obj(i));
                }
            },
            py::keep_alive<1, 2>(),
            "Extend the ``Pdf`` by adding pages from another ``Pdf.pages``.",
            py::arg("other"))
        .def(
            "extend",
            [](PageList &pl, py::iterable iterable) {
                py::iterator it = iterable.attr("__iter__")();
                while (it != py::iterator::sentinel()) {
                    // assert_pyobject_is_page_obj(*it);
                    assert_pyobject_is_page_helper(*it);
                    pl.insert_page(pl.count(), *it);
                    ++it;
                }
            },
            py::keep_alive<1, 2>(),
            "Extend the ``Pdf`` by adding pages from an iterable of pages.",
            py::arg("iterable"))
        .def(
            "remove",
            [](PageList &pl, py::kwargs kwargs) {
                auto pnum = kwargs["p"].cast<py::ssize_t>();
                if (pnum <= 0) // Indexing past end is checked in .get_page
                    throw py::index_error(
                        "page access out of range in 1-based indexing");
                pl.delete_page(pnum - 1);
            },
            R"~~~(
            Remove a page (using 1-based numbering)

            Args:
                p (int): 1-based page number
            )~~~")
        .def(
            "index",
            [](PageList &pl, const QPDFObjectHandle &h) {
                return page_index(*pl.qpdf, h);
            },
            R"~~~(
            Given a pikepdf.Object that is a page, find the index.

            That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
            A ``ValueError`` exception is thrown if the page does not belong to
            to this ``Pdf``.
            )~~~")
        .def(
            "index",
            [](PageList &pl, const QPDFPageObjectHelper &poh) {
                return page_index(*pl.qpdf, poh.getObjectHandle());
            },
            R"~~~(
            Given a pikepdf.Page (page helper), find the index.

            That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
            A ``ValueError`` exception is thrown if the page does not belong to
            to this ``Pdf``.
            )~~~")
        .def("__repr__",
            [](PageList &pl) {
                return std::string("<pikepdf._qpdf.PageList len=") +
                       std::to_string(pl.count()) + std::string(">");
            })
        .def(
            "from_objgen",
            [](PageList &pl, int obj, int gen) {
                return from_objgen(*pl.qpdf, QPDFObjGen(obj, gen));
            },
            R"~~~(
            Given an "objgen" (object ID, generation), return the page.

            Raises an exception if no page matches .
            )~~~")
        .def(
            "from_objgen",
            [](PageList &pl, std::pair<int, int> objgen) {
                return from_objgen(*pl.qpdf, QPDFObjGen(objgen.first, objgen.second));
            },
            R"~~~(
            Given an "objgen" (object ID, generation), return the page.

            Raises an exception if no page matches .
            )~~~");
}

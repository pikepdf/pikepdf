// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"
#include "qpdf_pagelist.h"

#include <qpdf/QPDFPageObjectHelper.hh>
#include <qpdf/QPDFPageDocumentHelper.hh>
#include <qpdf/QPDFPageLabelDocumentHelper.hh>

static QPDFPageObjectHelper as_page_helper(py::handle obj)
{
    try {
        return obj.cast<QPDFPageObjectHelper>();
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

QPDFPageObjectHelper PageList::get_page(py::size_t index)
{
    auto pages = this->doc.getAllPages();
    if (index < pages.size())
        return pages.at(index);
    throw py::index_error("Accessing nonexistent PDF page number");
}

std::vector<QPDFPageObjectHelper> PageList::get_page_objs_impl(py::slice slice)
{
    py::size_t start, stop, step, slicelength;
    if (!slice.compute(this->count(), &start, &stop, &step, &slicelength))
        throw py::error_already_set(); // LCOV_EXCL_LINE
    std::vector<QPDFPageObjectHelper> result;
    result.reserve(slicelength);
    for (py::size_t i = 0; i < slicelength; ++i) {
        auto oh = this->get_page(start);
        result.push_back(oh);
        start += step;
    }
    return result;
}

py::list PageList::get_pages(py::slice slice)
{
    auto page_objs = this->get_page_objs_impl(slice);
    py::list result;
    for (auto &page_obj : page_objs) {
        result.append(py::cast(page_obj));
    }
    return result;
}

void PageList::set_page(py::size_t index, py::object obj)
{
    set_page(index, as_page_helper(obj));
}

void PageList::set_page(py::size_t index, QPDFPageObjectHelper page)
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
    std::vector<QPDFPageObjectHelper> results;
    py::iterator it = other.attr("__iter__")();

    // Unpack list into iterable, check that each object is a page but
    // don't save the handles yet
    for (; it != py::iterator::sentinel(); ++it) {
        results.push_back(as_page_helper(*it));
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
            this->set_page(start + (i * step), results.at(i));
        }
    } else {
        // For simple slices, we can replace differing sizes
        // meaning results.size() could be slicelength, or not
        // so insert all pages first (to ensure nothing is freed yet)
        // and then delete all pages we no longer need

        // Insert first to ensure we don't delete any pages we will need
        for (py::size_t i = 0; i < results.size(); ++i) {
            this->insert_page(start + i, results.at(i));
        }

        py::size_t del_start = start + results.size();
        for (py::size_t i = 0; i < slicelength; ++i) {
            this->delete_page(del_start);
        }
    }
}

void PageList::delete_page(py::size_t index)
{
    auto page = this->get_page(index);
    this->doc.removePage(page);
}

void PageList::delete_pages_from_iterable(py::slice slice)
{
    // See above: need a way to dec_ref pages with another owner
    // Get handles for all pages, then remove them, since page numbers shift
    // after delete
    auto kill_list = this->get_page_objs_impl(slice);
    for (auto page : kill_list) {
        this->doc.removePage(page);
    }
}

py::size_t PageList::count() { return this->doc.getAllPages().size(); }

QPDFPageObjectHelper PageList::page_from_object(py::handle obj)
{
    try {
        auto page = obj.cast<QPDFPageObjectHelper>();
        return page;
    } catch (py::cast_error &) {
        // Perhaps obj is a dictionary with Type=Name.Page
    }

    QPDFObjectHandle oh, indirect_oh;
    try {
        oh = obj.cast<QPDFObjectHandle>();
    } catch (py::cast_error &) {
        throw py::type_error("tried to insert object which is neither pikepdf.Page "
                             "nor pikepdf.Dictionary with Type=Name.Page");
    }

    python_warning("Implicit conversion of pikepdf.Dictionary to pikepdf.Page is "
                   "deprecated. Use pikepdf.Page(dictionary) instead.",
        PyExc_DeprecationWarning);

    bool copied = false;
    try {
        if (!oh.getOwningQPDF()) {
            // No owner means this is a direct object - try making it indirect
            indirect_oh = this->qpdf->makeIndirectObject(oh);
            copied      = true;
        } else {
            indirect_oh = oh;
        }
        if (!indirect_oh.isPageObject()) {
            // PDFs in the wild often have malformed page objects, but when we're
            // building new pages we might as enforce correctness. If you really
            // want a malformed PDF, you can break it after making it properly.
            throw py::type_error(std::string("only pages can be inserted - you tried "
                                             "to insert this as a page: ") +
                                 objecthandle_repr(oh));
        }
        return QPDFPageObjectHelper(indirect_oh);
    } catch (std::runtime_error &) {
        // If we created a new temporary indirect object to hold the page, and
        // failed to insert, delete the object we created as best we can.
        if (copied) {
            this->qpdf->replaceObject(
                indirect_oh.getObjGen(), QPDFObjectHandle::newNull());
        }
        throw;
    }
}

void PageList::insert_page(py::size_t index, QPDFPageObjectHelper page)
{
    if (index != this->count()) {
        auto refpage = this->get_page(index);
        this->doc.addPageAt(page, true, refpage);
    } else {
        this->doc.addPage(page, false);
    }
}

void PageList::append_page(QPDFPageObjectHelper page)
{
    this->doc.addPage(page, false);
}

QPDFPageObjectHelper from_objgen(QPDF &q, QPDFObjGen og)
{
    auto h = q.getObjectByObjGen(og);
    if (!h.isPageObject())
        throw py::value_error("Object is not a page");
    return QPDFPageObjectHelper(h);
}

QPDFPageObjectHelper PageListIterator::next()
{
    if (this->index >= this->pages.size()) {
        throw py::stop_iteration();
    }
    auto page = this->pages.at(this->index);
    this->index++;
    return page;
}

void init_pagelist(py::module_ &m)
{
    py::class_<PageListIterator>(m, "_PageListIterator")
        .def("__iter__", [](PageListIterator &it) { return it; })
        .def("__next__", &PageListIterator::next);

    py::class_<PageList>(m, "PageList")
        .def(
            "__getitem__",
            [](PageList &pl, py::ssize_t index) {
                auto uindex = uindex_from_index(pl, index);
                return pl.get_page(uindex);
            },
            py::return_value_policy::reference_internal)
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
            py::arg("pnum"))
        .def(
            "__iter__",
            [](PageList &pl) { return PageListIterator{pl, 0}; },
            py::keep_alive<0, 1>())
        .def(
            "insert",
            [](PageList &pl, py::ssize_t index, QPDFPageObjectHelper &page) {
                auto uindex = uindex_from_index(pl, index);
                pl.insert_page(uindex, page);
            },
            py::arg("index"), // LCOV_EXCL_LINE
            py::arg("obj"))
        .def(
            "insert",
            [](PageList &pl, py::ssize_t index, py::object obj) {
                throw py::type_error("only pikepdf.Page can be inserted to PageList");
            },
            py::arg("index"), // LCOV_EXCL_LINE
            py::arg("obj"))
        .def("reverse",
            [](PageList &pl) {
                py::slice ordinary_indices(0, pl.count(), 1);
                py::slice reversed{{}, {}, -1};
                py::list reversed_pages = pl.get_pages(reversed);
                pl.set_pages_from_iterable(ordinary_indices, reversed_pages);
            })
        .def(
            "append",
            [](PageList &pl, QPDFPageObjectHelper &page) { pl.append_page(page); },
            py::arg("page"))
        .def(
            "append",
            [](PageList &pl, py::handle h) {
                throw py::type_error("only pikepdf.Page can be appended to PageList");
            },
            py::arg("page"))
        .def(
            "extend",
            [](PageList &pl, PageList &other) {
                auto other_pages = other.doc.getAllPages();
                for (auto &page : other_pages) {
                    pl.append_page(page);
                }
            },
            py::arg("other"))
        .def(
            "extend",
            [](PageList &pl, py::iterable iterable) {
                py::iterator it = iterable.attr("__iter__")();
                while (it != py::iterator::sentinel()) {
                    pl.append_page(as_page_helper(*it));
                    ++it;
                }
            },
            py::arg("iterable"))
        .def("remove",
            [](PageList &pl, QPDFPageObjectHelper &page) {
                try {
                    pl.doc.removePage(page);
                } catch (const QPDFExc &) {
                    throw py::value_error("pikepdf.Page is not referenced in the PDF");
                }
            })
        .def(
            "remove",
            [](PageList &pl, py::ssize_t pnum) {
                if (pnum <= 0) // Indexing past end is checked in .get_page
                    throw py::index_error(
                        "page access out of range in 1-based indexing");
                pl.delete_page(pnum - 1);
            },
            py::kw_only(),
            py::arg("p"))
        .def("index",
            [](PageList &pl, const QPDFObjectHandle &h) {
                return page_index(*pl.qpdf, h);
            })
        .def("index",
            [](PageList &pl, const QPDFPageObjectHelper &poh) {
                return page_index(*pl.qpdf, poh.getObjectHandle());
            })
        .def("__repr__",
            [](PageList &pl) {
                return std::string("<pikepdf._core.PageList len=") +
                       std::to_string(pl.count()) + std::string(">");
            })
        .def("from_objgen",
            [](PageList &pl, int obj, int gen) {
                return from_objgen(*pl.qpdf, QPDFObjGen(obj, gen));
            })
        .def("from_objgen", [](PageList &pl, std::pair<int, int> objgen) {
            return from_objgen(*pl.qpdf, QPDFObjGen(objgen.first, objgen.second));
        });
}

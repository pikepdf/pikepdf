// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "qpdf_pagelist.h"
#include "locked_bindings.h"
#include "object.h"
#include "pikepdf.h"
#include "qpdf_lock.h"

#include <exception>
#include <optional>

#include <qpdf/QPDFPageDocumentHelper.hh>
#include <qpdf/QPDFPageLabelDocumentHelper.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

static bool page_has_widget(QPDFObjectHandle page)
{
    if (!page.isDictionary())
        return false;
    auto annots = page.getKey("/Annots");
    if (!annots.isArray())
        return false;
    for (auto &a : annots.aitems()) {
        if (a.isDictionaryOfType("", "/Widget"))
            return true;
    }
    return false;
}

static bool action_is_named_goto(QPDFObjectHandle a)
{
    if (!a.isDictionary())
        return false;
    if (!a.getKey("/S").isNameAndEquals("/GoTo"))
        return false;
    auto d = a.getKey("/D");
    return d.isString() || d.isName();
}

static bool page_has_named_dest(QPDFObjectHandle page)
{
    if (!page.isDictionary())
        return false;
    auto annots = page.getKey("/Annots");
    if (!annots.isArray())
        return false;
    for (auto &a : annots.aitems()) {
        if (!a.isDictionary())
            continue;
        auto dest = a.getKey("/Dest");
        if (dest.isString() || dest.isName())
            return true;
        if (action_is_named_goto(a.getKey("/A")))
            return true;
    }
    return false;
}

static void warn_page_copy(bool forms, bool dests)
{
    if (!forms && !dests)
        return;
    std::string what;
    if (forms && dests)
        what = "interactive form fields or named destinations";
    else if (forms)
        what = "interactive form fields";
    else
        what = "named destinations";
    std::string msg = "Copying pages from another Pdf with pages.extend() does not "
                      "preserve " +
                      what +
                      "; form fields may not display in Adobe "
                      "Acrobat and internal links may not resolve. Use "
                      "Pdf.add_pages_from() to preserve them.";
    auto category = py::module_::import_("pikepdf._exceptions").attr("PageCopyWarning");
    python_warning(msg.c_str(), category.ptr(), /*stacklevel=*/1);
}

static QPDFPageObjectHelper as_page_helper(py::handle obj)
{
    try {
        return py::cast<QPDFPageObjectHelper>(obj);
    } catch (const py::cast_error &) {
        throw py::type_error((
            std::string(
                "only pikepdf pages can be assigned to a page list; tried to assign ") +
            py::cast<std::string>(py::str(py::inst_name(obj))))
                .c_str());
    }
}

// A binding parameter that must be a page, and arrives already converted by
// as_page_helper(). The conversion is done in the type caster, as it is for
// EncodedObject, so that the page's Pdf is known when the locks are taken. Any
// object is accepted: get() raises the TypeError for one that is not a page.
class PageArgument {
public:
    PageArgument() = default;
    explicit PageArgument(QPDFPageObjectHelper page) : page_(std::move(page)) {}
    explicit PageArgument(std::exception_ptr error) : error_(std::move(error)) {}

    QPDFPageObjectHelper const &get() const
    {
        if (error_)
            std::rethrow_exception(error_);
        return *page_;
    }

    // The Pdf to lock, or nullptr for an unowned page or an object that is
    // not a page
    QPDF *owner() const
    {
        return page_ ? page_->getObjectHandle().getOwningQPDF() : nullptr;
    }

private:
    std::optional<QPDFPageObjectHelper> page_;
    std::exception_ptr error_;
};

template <>
struct LockOwner<PageArgument> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(PageArgument const &value) { return value.owner(); }
};

namespace nanobind {
namespace detail {
template <>
struct type_caster<PageArgument> {
    NB_TYPE_CASTER(PageArgument, const_name("object"))

    bool from_python(handle src, uint8_t, cleanup_list *) noexcept
    {
        try {
            value = PageArgument(as_page_helper(src));
        } catch (...) {
            value = PageArgument(std::current_exception());
        }
        return true;
    }
};
} // namespace detail
} // namespace nanobind

size_t uindex_from_index(PageList &pl, py::ssize_t index)
{
    if (index < 0)
        index += pl.count();
    if (index < 0) // Still
        throw py::index_error("Accessing nonexistent PDF page number");
    size_t uindex = index;
    return uindex;
}

QPDFPageObjectHelper PageList::get_page(size_t index)
{
    auto pages = doc.getAllPages();
    if (index < pages.size())
        return pages.at(index);
    throw py::index_error("Accessing nonexistent PDF page number");
}

std::vector<QPDFPageObjectHelper> PageList::get_page_objs_impl(py::slice slice)
{
    auto [start, stop, step, slicelength] = slice.compute(count());
    std::vector<QPDFPageObjectHelper> result;
    result.reserve(slicelength);
    for (size_t i = 0; i < slicelength; ++i) {
        auto oh = get_page(start);
        result.push_back(oh);
        start += step;
    }
    return result;
}

py::list PageList::get_pages(py::slice slice)
{
    auto page_objs = get_page_objs_impl(slice);
    py::list result;
    for (auto &page_obj : page_objs) {
        result.append(py::cast(page_obj));
    }
    return result;
}

void PageList::set_page(size_t index, py::object obj)
{
    set_page(index, as_page_helper(obj));
}

void PageList::set_page(size_t index, QPDFPageObjectHelper page)
{
    insert_page(index, page);
    if (index != count()) {
        delete_page(index + 1);
    }
}

// Unpack an iterable into pages, checking that each item is a page. This runs
// arbitrary Python code, so it is done before any lock is taken.
static std::vector<QPDFPageObjectHelper> page_helpers_from_iterable(py::iterable other)
{
    std::vector<QPDFPageObjectHelper> results;
    py::iterator it = py::iter(other);
    for (; it != py::iterator::sentinel(); ++it) {
        results.push_back(as_page_helper(*it));
    }
    return results;
}

// The documents that must be locked to insert *pages* into *pl*: the
// destination, and every document a page is copied from. qpdf reads the
// source document while it copies a foreign page.
static std::vector<QPDF *> page_owners(
    PageList &pl, std::vector<QPDFPageObjectHelper> const &pages)
{
    std::vector<QPDF *> owners{pl.qpdf.get()};
    for (auto const &page : pages)
        owners.push_back(page.getObjectHandle().getOwningQPDF());
    return owners;
}

void PageList::set_pages_from_iterable(py::slice slice, py::iterable other)
{
    set_pages(slice, page_helpers_from_iterable(other));
}

void PageList::set_pages(
    py::slice slice, std::vector<QPDFPageObjectHelper> const &results)
{
    auto [start, stop, step, slicelength] = slice.compute(count());

    if (step != 1) {
        // For an extended slice we must be replace an equal number of pages
        if (results.size() != slicelength) {
            throw py::value_error(
                (std::string("attempt to assign sequence of length ") +
                    std::to_string(results.size()) +
                    std::string(" to extended slice of size ") +
                    std::to_string(slicelength))
                    .c_str());
        }
        for (size_t i = 0; i < slicelength; ++i) {
            set_page(start + (i * step), results.at(i));
        }
    } else {
        // For simple slices, we can replace differing sizes
        // meaning results.size() could be slicelength, or not
        // so insert all pages first (to ensure nothing is freed yet)
        // and then delete all pages we no longer need

        // Insert first to ensure we don't delete any pages we will need
        for (size_t i = 0; i < results.size(); ++i) {
            insert_page(start + i, results.at(i));
        }

        size_t del_start = start + results.size();
        for (size_t i = 0; i < slicelength; ++i) {
            delete_page(del_start);
        }
    }
}

void PageList::delete_page(size_t index)
{
    auto page = get_page(index);
    doc.removePage(page);
}

void PageList::delete_pages_from_iterable(py::slice slice)
{
    // See above: need a way to dec_ref pages with another owner
    // Get handles for all pages, then remove them, since page numbers shift
    // after delete
    auto kill_list = get_page_objs_impl(slice);
    for (auto page : kill_list) {
        doc.removePage(page);
    }
}

size_t PageList::count()
{
    return doc.getAllPages().size();
}

// A page inserted from another document is copied by qpdf, and a page built in
// Python has direct children that belong to no document at all. Either way the
// page now lives in this document, so give its direct children this document as
// their owner, exactly as if the page had been parsed from this file.
void PageList::adopt_page_at(size_t index)
{
    adopt_children_into(qpdf.get(), get_page(index).getObjectHandle());
}

void PageList::insert_page(size_t index, QPDFPageObjectHelper page)
{
    if (index != count()) {
        auto refpage = get_page(index);
        doc.addPageAt(page, true, refpage);
    } else {
        doc.addPage(page, false);
    }
    adopt_page_at(index);
}

void PageList::append_page(QPDFPageObjectHelper page)
{
    doc.addPage(page, false);
    adopt_page_at(count() - 1);
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
    if (index_.load() >= pages_.size())
        throw py::stop_iteration();
    // Claim a position: threads that share the iterator each get a different
    // one, and those that claim one past the end have reached the end.
    size_t index = index_.fetch_add(1);
    if (index >= pages_.size())
        throw py::stop_iteration();
    return pages_[index];
}

void init_pagelist(py::module_ &m)
{
    locked_class_<PageListIterator>(
        m, "_PageListIterator", py::type_slots(pikepdf_gc_slots))
        .def("__iter__", [](PageListIterator &it) { return it; })
        .def("__next__", &PageListIterator::next);

    locked_class_<PageList>(m, "PageList", py::type_slots(pikepdf_gc_slots))
        .def(
            "__getitem__",
            [](PageList &pl, py::ssize_t index) {
                auto uindex = uindex_from_index(pl, index);
                return pl.get_page(uindex);
            },
            py::rv_policy::reference_internal)
        .def("__getitem__",
            [](PageList &pl, py::slice slice) { return pl.get_pages(slice); })
        .def("__setitem__",
            [](PageList &pl, py::ssize_t index, PageArgument const &obj) {
                auto page = obj.get();
                auto uindex = uindex_from_index(pl, index);
                pl.set_page(uindex, page);
            })
        .def("__setitem__",
            // Which Pdfs the pages come from is not known until the iterable
            // has been unpacked. That runs arbitrary Python code, so it is
            // done with no lock held, and all the locks are then taken
            // together, in the registry's order. The wrapper would lock this
            // Pdf first, on its own.
            unlocked([](PageList &pl, py::slice slice, py::iterable other) {
                auto pages = page_helpers_from_iterable(other);
                MultiQpdfLockGuard lock(page_owners(pl, pages));
                pl.set_pages(slice, pages);
            }))
        .def("__delitem__",
            [](PageList &pl, py::ssize_t index) {
                auto uindex = uindex_from_index(pl, index);
                pl.delete_page(uindex);
            })
        .def("__delitem__",
            [](PageList &pl, py::slice slice) { pl.delete_pages_from_iterable(slice); })
        .def("__len__", [](PageList &pl) { return pl.count(); })
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
        .def("insert",
            // Only raises: uses no Pdf
            unlocked([](PageList &pl, py::ssize_t index, py::object obj) {
                throw py::type_error("only pikepdf.Page can be inserted to PageList");
            }),
            py::arg("index"), // LCOV_EXCL_LINE
            py::arg("obj"))
        .def("reverse",
            [](PageList &pl) {
                size_t n = pl.count();
                py::slice ordinary_indices((Py_ssize_t)0, (Py_ssize_t)n, (Py_ssize_t)1);
                py::object none_obj = py::none();
                py::slice reversed(none_obj, none_obj, py::int_(-1));
                py::list reversed_pages = pl.get_pages(reversed);
                pl.set_pages_from_iterable(
                    ordinary_indices, py::borrow<py::iterable>(reversed_pages));
            })
        .def(
            "append",
            [](PageList &pl, QPDFPageObjectHelper &page) { pl.append_page(page); },
            py::arg("page"))
        .def("append",
            // Only raises: uses no Pdf
            unlocked([](PageList &pl, py::handle h) {
                throw py::type_error("only pikepdf.Page can be appended to PageList");
            }),
            py::arg("page"))
        .def(
            "extend",
            [](PageList &pl, PageList &other) {
                auto other_pages = other.doc.getAllPages();
                if (other.qpdf.get() != pl.qpdf.get()) {
                    bool forms = false, dests = false;
                    for (auto &page : other_pages) {
                        auto h = page.getObjectHandle();
                        forms = forms || page_has_widget(h);
                        dests = dests || page_has_named_dest(h);
                        if (forms && dests)
                            break;
                    }
                    warn_page_copy(forms, dests);
                }
                for (auto &page : other_pages) {
                    pl.append_page(page);
                }
            },
            py::arg("other"))
        .def("extend",
            // Unpacks the iterable and then takes every lock together, as
            // slice assignment does and for the same reason.
            unlocked([](PageList &pl, py::iterable iterable) {
                auto pages = page_helpers_from_iterable(iterable);
                MultiQpdfLockGuard lock(page_owners(pl, pages));
                bool forms = false, dests = false;
                for (auto &page : pages) {
                    auto h = page.getObjectHandle();
                    if (h.getOwningQPDF() != pl.qpdf.get()) {
                        forms = forms || page_has_widget(h);
                        dests = dests || page_has_named_dest(h);
                    }
                    pl.append_page(page);
                }
                warn_page_copy(forms, dests);
            }),
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

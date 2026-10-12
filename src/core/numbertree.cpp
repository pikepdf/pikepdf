// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "locked_bindings.h"
#include "object.h"
#include "pikepdf.h"

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFNumberTreeObjectHelper.hh>
#include <qpdf/Types.h>

using numtree_number = QPDFNumberTreeObjectHelper::numtree_number;

using NumberTree = QPDFNumberTreeObjectHelper;

void init_numbertree(py::module_ &m)
{
    locked_class_<NumberTree, QPDFObjectHelper>(
        m, "NumberTree", py::type_slots(pikepdf_gc_slots))
        .def(
            "__init__",
            [](NumberTree *self, QPDFObjectHandle &oh, bool auto_repair) {
                QPDF *owner = live_owner(oh);
                if (!owner)
                    throw py::value_error(
                        "NumberTree must wrap a Dictionary that is owned by a Pdf");
                new (self) NumberTree(oh, *owner, auto_repair);
            },
            py::arg("oh"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_static(
            "new",
            [](QPDF &pdf, bool auto_repair = true) {
                return NumberTree::newEmpty(pdf, auto_repair);
            },
            py::arg("pdf"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def("__contains__",
            [](NumberTree &nt, numtree_number idx) { return nt.hasIndex(idx); })
        .def("__contains__",
            // Only an int can be a key
            unlocked([](NumberTree &, py::object) { return false; }),
            py::arg("key").none())
        .def("__getitem__",
            [](NumberTree &nt, numtree_number key) {
                QPDFObjectHandle oh;
                if (nt.findObject(key, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::index_error(std::to_string(key).c_str());
            })
        .def("__setitem__",
            [](NumberTree &nt, numtree_number key, EncodedObject const &value) {
                auto tree = nt.getObjectHandle();
                auto *owner = live_owner(tree);
                refuse_foreign_indirect(value.get(), owner);
                nt.insert(key, adopt_into(owner, value.get()));
            })
        .def("__delitem__", [](NumberTree &nt, numtree_number key) { nt.remove(key); })
        .def("__iter__",
            [](NumberTree &nt) {
                // The keys as they are now: see NameTree.__iter__
                py::list keys;
                for (auto it = nt.begin(); it != nt.end(); ++it)
                    keys.append(py::cast((*it).first));
                return py::iter(keys);
            })
        .def("_as_map", [](NumberTree &nt) { return nt.getAsMap(); })
        .def("__len__", [](NumberTree &nt) { return nt.getAsMap().size(); });
}

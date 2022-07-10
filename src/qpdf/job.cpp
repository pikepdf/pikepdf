/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2019, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <iostream>
#include <streambuf>
#include <qpdf/QPDFJob.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

using namespace py::literals;

struct pyprint_redirect : private std::streambuf, public std::ostream {
    pyprint_redirect(py::object output) : std::ostream(this), output(output) {}

private:
    int overflow(int c) override
    {
        py::print(char(c), "file"_a = this->output);
        return 0;
    }
    py::object output;
};

void init_job(py::module_ &m)
{
    py::class_<QPDFJob::Config, std::shared_ptr<QPDFJob::Config>> jobconfig(
        m, "JobConfig");

    py::class_<QPDFJob>(m, "Job")
        .def(py::init([](const std::string &json, bool partial) {
            QPDFJob job;
            job.initializeFromJson(json, partial);
            job.setMessagePrefix("pikepdf");
            return job;
        }))
        .def_property_readonly("config", &QPDFJob::config)
        .def("check_configuration", &QPDFJob::checkConfiguration)
        .def_property_readonly("creates_output", &QPDFJob::createsOutput)
        .def_property(
            "message_prefix",
            []() {
                //&QPDFJob::getMessagePrefix
                throw py::notimpl_error(
                    "QPDFJob::getMessagePrefix not available in qpdf 10.6.3");
            },
            &QPDFJob::setMessagePrefix)
        .def("run", &QPDFJob::run)
        .def_property_readonly("has_warnings", &QPDFJob::hasWarnings)
        .def_property_readonly("exit_code", &QPDFJob::getExitCode)
        .def_property_readonly("encryption_status", &QPDFJob::getEncryptionStatus);
}
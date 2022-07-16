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

    virtual ~pyprint_redirect()
    {
        py::gil_scoped_acquire{};
        // output = py::none();
    }

private:
    int overflow(int c) override
    {
        py::gil_scoped_acquire{};
        py::print(char(c), "file"_a = this->output, "end"_a = "");
        return 0;
    }
    py::object output;
};

std::unique_ptr<pyprint_redirect> py_stdout;
std::unique_ptr<pyprint_redirect> py_stderr;

void set_job_defaults(QPDFJob &job)
{
    if (!py_stdout) {
        py::gil_scoped_acquire{};
        py_stdout = std::make_unique<pyprint_redirect>(
            py::module_::import("sys").attr("stdout"));
    }
    if (!py_stderr) {
        py::gil_scoped_acquire{};
        py_stderr = std::make_unique<pyprint_redirect>(
            py::module_::import("sys").attr("stderr"));
    }

    job.setMessagePrefix("pikepdf");
    job.setOutputStreams(py_stdout.get(), py_stderr.get());
}

void init_job(py::module_ &m)
{
    py::class_<QPDFJob::Config, std::shared_ptr<QPDFJob::Config>> jobconfig(
        m, "JobConfig");

    py::class_<QPDFJob>(m, "Job")
        .def_property_readonly_static("json_out_schema_v1",
            [](const py::object &) { return QPDFJob::json_out_schema_v1(); })
        .def_property_readonly_static("job_json_schema_v1",
            [](const py::object &) { return QPDFJob::job_json_schema_v1(); })
        .def(py::init([](const std::string &json, bool partial) {
            QPDFJob job;
            job.initializeFromJson(json, partial);
            set_job_defaults(job);
            return job;
        }),
            py::arg("json"),
            py::kw_only(),
            py::arg("partial") = true)
        .def(py::init(
                 [](const std::vector<std::string> &args, std::string const &progname) {
                     QPDFJob job;
                     std::vector<const char *> cstrings;
                     cstrings.reserve(args.size() + 1);

                     for (auto &arg : args) {
                         cstrings.push_back(arg.c_str());
                     }
                     cstrings.push_back(nullptr);

                     job.initializeFromArgv(cstrings.data(), progname.c_str());
                     set_job_defaults(job);
                     return job;
                 }),
            py::arg("args"),
            py::kw_only(),
            py::arg("progname") = "pikepdf")
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
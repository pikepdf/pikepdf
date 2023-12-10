// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <iostream>
#include <streambuf>
#include <qpdf/QPDFJob.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

void set_job_defaults(QPDFJob &job) { job.setMessagePrefix("pikepdf"); }

QPDFJob job_from_json_str(const std::string &json)
{
    QPDFJob job;
    bool partial = false;
    job.initializeFromJson(json, partial);
    set_job_defaults(job);
    return job;
}

void init_job(py::module_ &m)
{
    py::class_<QPDFJob>(m, "Job")
        .def_static(
            "json_out_schema",
            [](int schema = JSON::LATEST) { return QPDFJob::json_out_schema(schema); },
            py::kw_only(),
            py::arg("schema") = JSON::LATEST)
        .def_static(
            "job_json_schema",
            [](int schema = QPDFJob::LATEST_JOB_JSON) {
                return QPDFJob::job_json_schema(schema);
            },
            py::kw_only(),
            py::arg("schema") = QPDFJob::LATEST_JOB_JSON)
        .def_readonly_static("EXIT_ERROR", &QPDFJob::EXIT_ERROR)
        .def_readonly_static("EXIT_WARNING", &QPDFJob::EXIT_WARNING)
        .def_readonly_static("EXIT_IS_NOT_ENCRYPTED", &QPDFJob::EXIT_IS_NOT_ENCRYPTED)
        .def_readonly_static("EXIT_CORRECT_PASSWORD", &QPDFJob::EXIT_CORRECT_PASSWORD)
        .def_readonly_static("LATEST_JOB_JSON", &QPDFJob::LATEST_JOB_JSON)
        .def_readonly_static("LATEST_JSON", &JSON::LATEST)
        .def(py::init(&job_from_json_str),
            py::arg("json") // LCOV_EXCL_LINE
            )
        .def(py::init([](py::dict &json_dict) {
            auto json_dumps  = py::module_::import("json").attr("dumps");
            py::str json_str = json_dumps(json_dict);
            return job_from_json_str(std::string(json_str));
        }),
            py::arg("json_dict"))
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
        .def("check_configuration", &QPDFJob::checkConfiguration)
        .def_property_readonly("creates_output",
            &QPDFJob::createsOutput // LCOV_EXCL_LINE
            )
        .def_property(
            "message_prefix", &QPDFJob::getMessagePrefix, &QPDFJob::setMessagePrefix)
        .def("run", &QPDFJob::run)
        .def("create_pdf",
            [](QPDFJob &job) { return std::shared_ptr<QPDF>(job.createQPDF()); })
        .def("write_pdf", &QPDFJob::writeQPDF, py::arg("pdf"))
        .def_property_readonly("has_warnings", &QPDFJob::hasWarnings)
        .def_property_readonly("exit_code", &QPDFJob::getExitCode)
        .def_property_readonly("encryption_status", [](QPDFJob &job) {
            uint bits = job.getEncryptionStatus();
            py::dict result;
            result["encrypted"]          = bool(bits & qpdf_es_encrypted);
            result["password_incorrect"] = bool(bits & qpdf_es_password_incorrect);
            return result;
        });
}
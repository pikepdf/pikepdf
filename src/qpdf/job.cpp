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
    py::class_<QPDFJob>(m, "Job", R"~~~(
        Provides access to the QPDF job interface.

        All of the functionality of the ``qpdf`` command line program
        is now available to pikepdf through jobs.

        For further details:
            https://qpdf.readthedocs.io/en/stable/qpdf-job.html
    )~~~")
        .def_static(
            "json_out_schema",
            [](int schema = JSON::LATEST) { return QPDFJob::json_out_schema(schema); },
            py::kw_only(),
            py::arg("schema") = JSON::LATEST,
            "For reference, the QPDF JSON output schema is built-in.")
        .def_static(
            "job_json_schema",
            [](int schema = QPDFJob::LATEST_JOB_JSON) {
                return QPDFJob::job_json_schema(schema);
            },
            py::kw_only(),
            py::arg("schema") = QPDFJob::LATEST_JOB_JSON,
            "For reference, the QPDF job command line schema is built-in.")
        .def_readonly_static("EXIT_ERROR",
            &QPDFJob::EXIT_ERROR,
            "Exit code for a job that had an error.")
        .def_readonly_static("EXIT_WARNING",
            &QPDFJob::EXIT_WARNING,
            "Exit code for a job that had a warning.")
        .def_readonly_static("EXIT_IS_NOT_ENCRYPTED",
            &QPDFJob::EXIT_IS_NOT_ENCRYPTED,
            "Exit code for a job that provide a password when the input was not "
            "encrypted.")
        .def_readonly_static("EXIT_CORRECT_PASSWORD", &QPDFJob::EXIT_CORRECT_PASSWORD)
        .def_readonly_static("LATEST_JOB_JSON",
            &QPDFJob::LATEST_JOB_JSON,
            "Version number of the most recent job-JSON schema.")
        .def_readonly_static("LATEST_JSON",
            &JSON::LATEST,
            "Version number of the most recent QPDF-JSON schema.")
        .def(py::init(&job_from_json_str),
            py::arg("json"),
            "Create a Job from a string containing QPDF job JSON.")
        .def(py::init([](py::dict &json_dict) {
            auto json_dumps  = py::module_::import("json").attr("dumps");
            py::str json_str = json_dumps(json_dict);
            return job_from_json_str(std::string(json_str));
        }),
            py::arg("json_dict"),
            "Create a Job from a dict in QPDF job JSON schema.")
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
            py::arg("progname") = "pikepdf",
            R"~~~(
                Create a Job from command line arguments to the qpdf program.

                The first item in the ``args`` list should be equal to ``progname``,
                whose default is ``"pikepdf"``.

                Example:
                    job = Job(['pikepdf', '--check', 'input.pdf'])
                    job.run()
            )~~~")
        .def("check_configuration",
            &QPDFJob::checkConfiguration,
            "Checks if the configuration is valid; raises an exception if not.")
        .def_property_readonly("creates_output",
            &QPDFJob::createsOutput,
            "Returns True if the Job will create some sort of output file.")
        .def_property("message_prefix",
            &QPDFJob::getMessagePrefix,
            &QPDFJob::setMessagePrefix,
            "Allows manipulation of the prefix in front of all output messages.")
        .def("run", &QPDFJob::run, "Executes the job.")
        .def_property_readonly("has_warnings",
            &QPDFJob::hasWarnings,
            "After run(), returns True if there were warnings.")
        .def_property_readonly("exit_code",
            &QPDFJob::getExitCode,
            R"~~~(
            After run(), returns an integer exit code.

            Some exit codes have integer value. Their applicably is determined by
            context of the job being run.
            )~~~")
        .def_property_readonly(
            "encryption_status",
            [](QPDFJob &job) {
                uint bits = job.getEncryptionStatus();
                py::dict result;
                result["encrypted"]          = bool(bits & qpdf_es_encrypted);
                result["password_incorrect"] = bool(bits & qpdf_es_password_incorrect);
                return result;
            },
            "Returns a Python dictionary describing the encryption status.");
}
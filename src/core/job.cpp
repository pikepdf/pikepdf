// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <iostream>
#include <qpdf/QPDFJob.hh>
#include <streambuf>

#include "pikepdf.h"

void set_job_defaults(QPDFJob &job)
{
    job.setMessagePrefix("pikepdf");
}

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
    py::class_<QPDFJob>(m, "Job", py::type_slots(pikepdf_gc_slots))
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
        .def_ro_static("EXIT_ERROR", &QPDFJob::EXIT_ERROR)
        .def_ro_static("EXIT_WARNING", &QPDFJob::EXIT_WARNING)
        .def_ro_static("EXIT_IS_NOT_ENCRYPTED", &QPDFJob::EXIT_IS_NOT_ENCRYPTED)
        .def_ro_static("EXIT_CORRECT_PASSWORD", &QPDFJob::EXIT_CORRECT_PASSWORD)
        .def_ro_static("LATEST_JOB_JSON", &QPDFJob::LATEST_JOB_JSON)
        .def_ro_static("LATEST_JSON", &JSON::LATEST)
        .def(
            "__init__",
            [](QPDFJob *self, const std::string &json) {
                new (self) QPDFJob(job_from_json_str(json));
            },
            py::arg("json") // LCOV_EXCL_LINE
            )
        .def(
            "__init__",
            [](QPDFJob *self, py::dict &json_dict) {
                auto json_dumps = py::module_::import_("json").attr("dumps");
                py::str json_str = py::borrow<py::str>(json_dumps(json_dict));
                new (self) QPDFJob(job_from_json_str(py::cast<std::string>(json_str)));
            },
            py::arg("json_dict"))
        .def(
            "__init__",
            [](QPDFJob *self,
                const std::vector<std::string> &args,
                std::string const &progname) {
                new (self) QPDFJob();
                std::vector<const char *> cstrings;
                cstrings.reserve(args.size() + 1);

                for (auto &arg : args) {
                    cstrings.push_back(arg.c_str());
                }
                cstrings.push_back(nullptr);

                self->initializeFromArgv(cstrings.data(), progname.c_str());
                set_job_defaults(*self);
            },
            py::arg("args"),
            py::kw_only(),
            py::arg("progname") = "pikepdf")
        .def("check_configuration", &QPDFJob::checkConfiguration)
        .def_prop_ro("creates_output",
            &QPDFJob::createsOutput // LCOV_EXCL_LINE
            )
        .def_prop_rw(
            "message_prefix", &QPDFJob::getMessagePrefix, &QPDFJob::setMessagePrefix)
        .def("run", &QPDFJob::run)
        .def("create_pdf",
            [](QPDFJob &job) { return std::shared_ptr<QPDF>(job.createQPDF()); })
        .def("write_pdf", &QPDFJob::writeQPDF, py::arg("pdf"))
        .def_prop_ro("has_warnings", &QPDFJob::hasWarnings)
        .def_prop_ro("exit_code", &QPDFJob::getExitCode)
        .def_prop_ro("encryption_status", [](QPDFJob &job) {
            uint bits = job.getEncryptionStatus();
            py::dict result;
            result["encrypted"] = bool(bits & qpdf_es_encrypted);
            result["password_incorrect"] = bool(bits & qpdf_es_password_incorrect);
            return result;
        });
}
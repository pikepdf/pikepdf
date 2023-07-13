# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import json

import pytest

from pikepdf import Job, JobUsageError, Pdf


def test_job_from_argv(resources):
    job = Job(['pikepdf', '--check', str(resources / 'outlines.pdf')])
    job.check_configuration()
    job.message_prefix = 'foo'
    assert job.message_prefix == 'foo'
    assert not job.creates_output
    assert not job.has_warnings
    assert job.exit_code == 0
    job.run()
    assert job.exit_code == 0
    assert not job.encryption_status["encrypted"]
    assert not job.encryption_status["password_incorrect"]


def test_job_from_json(resources, outpdf):
    job_json = {}
    job_json['inputFile'] = str(resources / 'outlines.pdf')
    job_json['outputFile'] = str(outpdf)
    job = Job(json.dumps(job_json))
    job.check_configuration()
    job.run()
    assert job.exit_code == 0

    job_json = {}
    job_json['inputFile'] = str(resources / 'outlines.pdf')
    job_json['outputFile'] = str(outpdf)
    job = Job(job_json)
    job.check_configuration()
    job.run()
    assert job.exit_code == 0


def test_job_in_stages(resources, outpdf):
    job_json = {}
    job_json['inputFile'] = str(resources / 'outlines.pdf')
    job_json['outputFile'] = str(outpdf)
    job = Job(json.dumps(job_json))
    job.check_configuration()
    pdf = job.create_pdf()
    del pdf.pages[1]
    job.write_pdf(pdf)
    assert job.exit_code == 0
    with Pdf.open(outpdf) as pdf:
        assert len(pdf.pages) == 1


def test_job_from_invalid_json():
    job_json = {}
    job_json['invalidJsonSetting'] = '123'
    with pytest.raises(RuntimeError):
        _ = Job(job_json)

    job_json2 = {}
    job_json2 = {'inputFile': []}
    with pytest.raises(JobUsageError):
        _ = Job(job_json2)


def test_schemas():
    assert isinstance(Job.LATEST_JSON, int)
    assert isinstance(Job.json_out_schema(), str)

    assert isinstance(Job.LATEST_JOB_JSON, int)
    assert isinstance(Job.job_json_schema(), str)

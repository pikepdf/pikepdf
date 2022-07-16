from pikepdf import Job


def test_job_from_argv(resources, outpdf):
    job = Job(['--check', str(resources / 'outlines.pdf'), str(outpdf)])
    job.check_configuration()
    assert job.creates_output
    assert not job.has_warnings
    assert job.exit_code == 0
    assert job.encryption_status == 0


def test_schemas():
    assert isinstance(Job.json_out_schema_v1, str)
    assert isinstance(Job.job_json_schema_v1, str)

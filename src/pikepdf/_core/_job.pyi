# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/job.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar, overload

from pikepdf._core._qpdf import Pdf

class Job:
    """Provides access to the qpdf job interface.

    All of the functionality of the ``qpdf`` command line program
    is now available to pikepdf through jobs.

    For further details:
        https://qpdf.readthedocs.io/en/stable/qpdf-job.html
    """

    EXIT_ERROR: ClassVar[int] = 2
    """Exit code for a job that had an error."""
    EXIT_WARNING: ClassVar[int] = 3
    """Exit code for a job that had a warning."""
    EXIT_IS_NOT_ENCRYPTED: ClassVar[int] = 2
    """Exit code for a job that provide a password when the input was not encrypted."""
    EXIT_CORRECT_PASSWORD: ClassVar[int] = 3
    LATEST_JOB_JSON: ClassVar[int]
    """Version number of the most recent job-JSON schema."""
    LATEST_JSON: ClassVar[int]
    """Version number of the most recent qpdf-JSON schema."""

    @staticmethod
    def json_out_schema(*, schema: int) -> str:
        """For reference, the qpdf JSON output schema is built-in."""
    @staticmethod
    def job_json_schema(*, schema: int) -> str:
        """For reference, the qpdf job command line schema is built-in."""
    @overload
    def __init__(self, json: str) -> None: ...
    @overload
    def __init__(self, json_dict: Mapping) -> None: ...
    @overload
    def __init__(
        self, args: Sequence[str | bytes], *, progname: str = 'pikepdf'
    ) -> None: ...
    def __init__(self, *args, **kwargs) -> None:
        """Create a Job from command line arguments to the qpdf program.

        The first item in the ``args`` list should be equal to ``progname``,
        whose default is ``"pikepdf"``.

        Example:
            job = Job(['pikepdf', '--check', 'input.pdf'])
            job.run()
        """
    def check_configuration(self) -> None:
        """Checks if the configuration is valid; raises an exception if not."""
    @property
    def creates_output(self) -> bool:
        """Returns True if the Job will create some sort of output file."""
    @property
    def message_prefix(self) -> str:
        """Allows manipulation of the prefix in front of all output messages."""
    def run(self) -> None:
        """Executes the job."""
    def create_pdf(self):
        """Executes the first stage of the job."""
    def write_pdf(self, pdf: Pdf):
        """Executes the second stage of the job."""
    @property
    def has_warnings(self) -> bool:
        """After run(), returns True if there were warnings."""
    @property
    def exit_code(self) -> int:
        """After run(), returns an integer exit code.

        The meaning of exit code depends on the details of the Job that was run.
        Details are subject to change in libqpdf. Use properties ``has_warnings``
        and ``encryption_status`` instead.
        """
    @property
    def encryption_status(self) -> dict[str, bool]:
        """Returns a Python dictionary describing the encryption status."""

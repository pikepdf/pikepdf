# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Thread safety stress tests for the smaller bindings.

A companion to test_threading.py, in the same style and with the same helpers,
for the classes that are not a Pdf's own but can be handed one of its objects
(Rectangle, Matrix, NamePath, Job), and for the object containers
(_ObjectList, _ObjectMapping), which belong to no Pdf and so are protected by
a lock of their own.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from test_threading import N_THREADS, run_n

import pikepdf
from pikepdf import (
    Array,
    Dictionary,
    Integer,
    Job,
    Matrix,
    Name,
    NamePath,
    Pdf,
    Real,
    Rectangle,
)
from pikepdf._core import _ObjectList, _ObjectMapping

# A deadlock must fail the test rather than hang the run. See test_threading.py
pytestmark = pytest.mark.timeout(120, method='thread')

N_BOXES = 40


@pytest.fixture(scope='module')
def boxes_pdf_bytes():
    """A saved Pdf of arrays whose every number is its own indirect object.

    Reading an array as a rectangle or a matrix makes qpdf load each number
    from the file. The numbers are made indirect in explicit conversion mode,
    so that they are not stored directly on the way.
    """
    pdf = Pdf.new()
    pdf.add_blank_page()
    rects, matrices, names = Array(), Array(), Array()
    with pikepdf.explicit_conversion():
        for n in range(N_BOXES):
            rects.append(
                Array([pdf.make_indirect(Integer(v)) for v in (0, 0, n + 1, n + 2)])
            )
            matrices.append(
                Array([pdf.make_indirect(Real(str(v))) for v in (1, 0, 0, 1, n, -n)])
            )
            names.append(pdf.make_indirect(Name(f'/Key{n}')))
        pdf.Root.Rects = pdf.make_indirect(rects)
        pdf.Root.Matrices = pdf.make_indirect(matrices)
        pdf.Root.KeyNames = pdf.make_indirect(names)
        pdf.Root.Key3 = Dictionary(Found=3)
    out = BytesIO()
    pdf.save(out)
    return out.getvalue()


def test_stress_rectangle_and_matrix_from_cold_objects(boxes_pdf_bytes):
    """Rectangles and matrices built from unread arrays have the file's values."""
    for _ in range(5):
        with Pdf.open(BytesIO(boxes_pdf_bytes)) as pdf, pikepdf.explicit_conversion():
            rects = pdf.Root.Rects
            matrices = pdf.Root.Matrices

            def read(i, rects=rects, matrices=matrices):
                with pikepdf.explicit_conversion():
                    for n in range(i % 4, N_BOXES, 4):
                        rect = Rectangle(rects[n])
                        assert (rect.llx, rect.lly, rect.urx, rect.ury) == (
                            0,
                            0,
                            n + 1,
                            n + 2,
                        )
                        matrix = Matrix(matrices[n])
                        assert matrix.shorthand == (1, 0, 0, 1, n, -n)

            run_n(read)


def test_stress_namepath_from_cold_names(boxes_pdf_bytes):
    """A NamePath built from a Name that has not been read uses its value."""
    for _ in range(5):
        with Pdf.open(BytesIO(boxes_pdf_bytes)) as pdf, pikepdf.explicit_conversion():
            names = pdf.Root.KeyNames
            root = pdf.Root

            def read(i, names=names, root=root):
                with pikepdf.explicit_conversion():
                    for n in range(i % 4, N_BOXES, 4):
                        assert repr(NamePath(names[n])) == f'NamePath.Key{n}'
                        assert repr(NamePath[names[n]]) == f'NamePath.Key{n}'
                        assert repr(NamePath.A(names[n])) == f'NamePath.A.Key{n}'
                    assert int(root[NamePath(names[3]).Found]) == 3

            run_n(read)


def test_stress_job_writes_pdf_while_it_is_read(boxes_pdf_bytes, tmp_path):
    """Job.write_pdf writes a Pdf that other threads are reading."""
    for round_ in range(3):
        infile = tmp_path / f'in{round_}.pdf'
        infile.write_bytes(boxes_pdf_bytes)
        outfile = tmp_path / f'out{round_}.pdf'
        job = Job(['pikepdf', str(infile), str(outfile)])
        pdf = job.create_pdf()

        def work(i, job=job, pdf=pdf):
            if i == 0:
                job.write_pdf(pdf)
                return
            with pikepdf.explicit_conversion():
                for n in range(i % 4, N_BOXES, 4):
                    assert [int(v) for v in pdf.Root.Rects[n]] == [0, 0, n + 1, n + 2]
                    assert str(pdf.Root.KeyNames[n]) == f'/Key{n}'

        run_n(work)
        with Pdf.open(outfile) as check:
            assert len(check.Root.Rects) == N_BOXES
            assert [int(v) for v in check.Root.Rects[7]] == [0, 0, 8, 9]
        pdf.close()


def test_stress_object_list_shared():
    """Threads changing and reading one _ObjectList lose and corrupt nothing."""
    per_thread = 200
    shared = _ObjectList()
    other = _ObjectList()
    other.extend([Name.A, 1, 'two'])

    def work(i):
        for n in range(per_thread):
            if i % 2:
                shared.append(Dictionary(T=i, N=n))
            else:
                shared.append(1000 * i + n)
            if n % 20 == 0:
                assert 1000 * 99 not in shared
                assert shared.count(-1) == 0
                assert shared != other
                assert repr(shared).startswith('pikepdf._core._ObjectList([')
                assert len(list(shared)) >= n

    run_n(work)
    assert len(shared) == per_thread * N_THREADS
    for i in range(0, N_THREADS, 2):
        for n in range(per_thread):
            assert 1000 * i + n in shared

    def remove(i):
        if i % 2 == 0:
            for n in range(per_thread):
                shared.remove(1000 * i + n)

    run_n(remove)
    assert len(shared) == per_thread * (N_THREADS // 2)
    assert all(isinstance(item, Dictionary) for item in shared)


def test_stress_object_mapping_shared():
    """Threads changing and reading one _ObjectMapping lose nothing."""
    per_thread = 200
    shared = _ObjectMapping()
    other = _ObjectMapping()
    other['/X'] = 1

    def work(i):
        for n in range(per_thread):
            shared[f'/K{i}_{n}'] = Dictionary(T=i, N=n)
            assert f'/K{i}_{n}' in shared
            assert shared[f'/K{i}_{n}'].N == n
            if n % 20 == 0:
                assert shared != other
                assert shared.get('/Missing') is None
                try:
                    assert len(list(shared.keys())) >= n
                except RuntimeError as e:
                    # As for a dict, iteration notices a concurrent change
                    assert 'changed size during iteration' in str(e)
        for n in range(0, per_thread, 2):
            del shared[f'/K{i}_{n}']

    run_n(work)
    assert len(shared) == per_thread // 2 * N_THREADS
    for i in range(N_THREADS):
        assert shared[f'/K{i}_1'].T == i
        assert f'/K{i}_0' not in shared

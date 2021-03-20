# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from math import cos, pi, sin


class PdfMatrix:
    """
    Support class for PDF content stream matrices

    PDF content stream matrices are 3x3 matrices summarized by a shorthand
    ``(a, b, c, d, e, f)`` which correspond to the first two column vectors.
    The final column vector is always ``(0, 0, 1)`` since this is using
    `homogenous coordinates <https://en.wikipedia.org/wiki/Homogeneous_coordinates>`_.

    PDF uses row vectors.  That is, ``vr @ A'`` gives the effect of transforming
    a row vector ``vr=(x, y, 1)`` by the matrix ``A'``.  Most textbook
    treatments use ``A @ vc`` where the column vector ``vc=(x, y, 1)'``.

    (``@`` is the Python matrix multiplication operator.)

    Addition and other operations are not implemented because they're not that
    meaningful in a PDF context (they can be defined and are mathematically
    meaningful in general).

    PdfMatrix objects are immutable. All transformations on them produce a new
    matrix.

    """

    def __init__(self, *args):
        # fmt: off
        if not args:
            self.values = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        elif len(args) == 6:
            a, b, c, d, e, f = map(float, args)
            self.values = ((a, b, 0),
                           (c, d, 0),
                           (e, f, 1))
        elif isinstance(args[0], PdfMatrix):
            self.values = args[0].values
        elif len(args[0]) == 6:
            a, b, c, d, e, f = map(float, args[0])
            self.values = ((a, b, 0),
                           (c, d, 0),
                           (e, f, 1))
        elif len(args[0]) == 3 and len(args[0][0]) == 3:
            self.values = (tuple(args[0][0]),
                           tuple(args[0][1]),
                           tuple(args[0][2]))
        else:
            raise ValueError('arguments')
        # fmt: on

    @staticmethod
    def identity():
        """Constructs and returns an identity matrix"""
        return PdfMatrix()

    def __matmul__(self, other):
        """Multiply this matrix by another matrix

        Can be used to concatenate transformations.

        """
        a = self.values
        b = other.values
        return PdfMatrix(
            [
                [
                    sum([float(i) * float(j) for i, j in zip(row, col)])
                    for col in zip(*b)
                ]
                for row in a
            ]
        )

    def scaled(self, x, y):
        """Concatenates a scaling matrix on this matrix"""
        return self @ PdfMatrix((x, 0, 0, y, 0, 0))

    def rotated(self, angle_degrees_ccw):
        """Concatenates a rotation matrix on this matrix"""
        angle = angle_degrees_ccw / 180.0 * pi
        c, s = cos(angle), sin(angle)
        return self @ PdfMatrix((c, s, -s, c, 0, 0))

    def translated(self, x, y):
        """Translates this matrix"""
        return self @ PdfMatrix((1, 0, 0, 1, x, y))

    @property
    def shorthand(self):
        """Return the 6-tuple (a,b,c,d,e,f) that describes this matrix"""
        return (self.a, self.b, self.c, self.d, self.e, self.f)

    @property
    def a(self):
        return self.values[0][0]

    @property
    def b(self):
        return self.values[0][1]

    @property
    def c(self):
        return self.values[1][0]

    @property
    def d(self):
        return self.values[1][1]

    @property
    def e(self):
        return self.values[2][0]

    @property
    def f(self):
        return self.values[2][1]

    def __eq__(self, other):
        if isinstance(other, PdfMatrix):
            return self.shorthand == other.shorthand
        return False

    def encode(self):
        """Encode this matrix in binary suitable for including in a PDF"""
        return '{:.6f} {:.6f} {:.6f} {:.6f} {:.6f} {:.6f}'.format(
            self.a, self.b, self.c, self.d, self.e, self.f
        ).encode()

    def __repr__(self):
        return 'pikepdf.Matrix(' + repr(self.values) + ')'

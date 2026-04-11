# SPDX-FileCopyrightText: 2025 @rakurtz
# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Parsing the matrixes in a PDF file."""

from __future__ import annotations

from logging import getLogger

from pikepdf._core import Matrix, Page
from pikepdf.models._content_stream import parse_content_stream

logger = getLogger(__name__)

# Operator names we dispatch on. Kept as plain strings (instead of module-level
# pikepdf.Operator instances) so that importing this module does not create
# long-lived pikepdf.Object instances that nanobind reports as leaks at
# interpreter shutdown.
_OP_CM = 'cm'  # "Concatenate Matrix": changes the current transformation matrix
_OP_DO = 'Do'  # "Draw Object"
_OP_STACK = 'q'  # Push the CTM onto the graphics state stack
_OP_POP = 'Q'  # Pop the CTM from the graphics state stack


class MatrixStack:
    """Tracks the CTM (current transformation matrix) in a PDF content stream.

    The CTM starts as the initial matrix and can be changed via the 'cm'
    (concatenate matrix) operator --> CTM = CTM x CM (with CTM and CM
    being 3x3 matrixes). Initial matrix is the identity matrix unless overridden.

    Furthermore can the CTM be stored to the stack via the 'q' operator.
    This save the CTM and subsequent 'cm' operators change a copy of that CTM
    --> 'q 1 0 0 1 0 0 cm'
    --> Copy CTM onto the stack and change the copy via 'cm'

    With the 'Q' operator the current CTM is replaced with the previous one from the
    stack.

    Error handling:
    1. Popping from an empty stack results in CTM being set to the initial matrix
    2. Multiplying with invalid operands sets the CTM to invalid
    3. Multiplying an invalid CTM with a valid CM results in an invalid CTM
    4. Stacking an invalid CTM results in a copy of that invalid CTM onto the stack
    --> All operations with an invalid CTM result in an invalid CTM
    --> The CTM is valid again when all invalid CTMs are popped off the stack
    """

    def __init__(self, initial_matrix: Matrix | None = None) -> None:
        """Initializing the stack with the initial matrix."""
        if initial_matrix is None:
            initial_matrix = Matrix.identity()
        self._initial_matrix = initial_matrix
        self._stack: list[Matrix | None] = [self._initial_matrix]

    def stack(self):
        """Copying the current CTM onto the stack."""
        self._stack.append(self._stack[-1])

    def pop(self):
        """Removing the current CTM from the stack.

        The stack is not permitted to underflow. If popped too many times, the CTM
        is set to the initial matrix. Some PDFs contain invalid content streams
        that would result in an underflow, therefore the initial matrix is used
        as a safe fallback.
        """
        assert len(self._stack) >= 1, "can't be empty"
        if len(self._stack) == 1:
            self._stack = [self._initial_matrix]
        else:
            self._stack.pop()

    def multiply(self, matrix: Matrix):
        """Multiplies the CTM with `matrix`. The result is not returned."""
        if self._stack[-1] is None:
            return
        else:
            self._stack[-1] = self._stack[-1] @ matrix

    def invalidate_current_transformation_matrix(self):
        """Registers the occurence of an invalid CM.

        See `# Error handling` for further informations.
        """
        self._stack[-1] = None

    @property
    def ctm(self) -> Matrix | None:
        """Returns the current transformation matrix or `None` if it's invalid."""
        return self._stack[-1]


def get_objects_with_ctm(
    page: Page, initial_matrix: Matrix | None = None
) -> list[tuple[str, Matrix]]:
    """Determines the current transformation matrix (CTM) for each drawn object.

    Filters objects with an invalid CTM.
    """
    if initial_matrix is None:
        initial_matrix = Matrix.identity()
    objects_with_ctm: list[
        tuple[str, Matrix]
    ] = []  # Stores the matrixes and the corresponding objects
    matrix_stack = MatrixStack(initial_matrix)
    for inst in parse_content_stream(page):
        operator, operands = inst.operator, inst.operands
        # Compare as strings - pikepdf.Operator.__eq__ supports comparison to
        # str / bytes, avoiding the need to allocate Operator instances.
        op_name = str(operator)
        if op_name == _OP_STACK:
            matrix_stack.stack()

        elif op_name == _OP_POP:
            matrix_stack.pop()

        elif op_name == _OP_CM:
            try:
                matrix_stack.multiply(Matrix(*operands))
            except TypeError:
                logger.debug(f"malformed operands for `cm` operator: {operands}")
                matrix_stack.invalidate_current_transformation_matrix()

        elif op_name == _OP_DO:
            name = str(operands[0])  # Name of the image (or other object)
            if matrix_stack.ctm is not None:
                objects_with_ctm.append(
                    (name, matrix_stack.ctm)
                )  # Explicit copying the CTM
            else:
                logger.debug(
                    f"skipping `Do` operator due to invalid CTM for object: {name}"
                )

    return objects_with_ctm

# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Pdf


@pytest.fixture
def form(resources):
    with Pdf.open(resources / 'form.pdf') as pdf:
        yield pdf


def test_acroform(form):
    acro = form.acroform
    assert acro.exists
    assert len(acro.fields) == 5


def test_appearances(form):
    acro = form.acroform
    acro.needs_appearences = True
    assert acro.needs_appearances is True
    acro.generate_appearances_if_needed()
    assert acro.needs_appearances is False


def test_text(form):
    field = form.acroform.get_fields_with_qualified_name('Text1')[0]
    assert field.fully_qualified_name == 'Text1'
    assert field.is_top_level
    assert field.is_text
    assert not field.is_checkbox
    assert not field.is_radio_button
    assert not field.is_pushbutton
    assert not field.is_choice


def test_button(form):
    field = form.acroform.get_fields_with_qualified_name('Button2')[0]
    assert field.fully_qualified_name == 'Button2'
    assert field.is_top_level
    assert not field.is_text
    assert not field.is_checkbox
    assert not field.is_radio_button
    assert field.is_pushbutton
    assert not field.is_choice


def test_checkbox(form):
    field = form.acroform.get_fields_with_qualified_name('Check Box3')[0]
    assert field.fully_qualified_name == 'Check Box3'
    assert field.is_top_level
    assert not field.is_text
    assert field.is_checkbox
    assert not field.is_radio_button
    assert not field.is_pushbutton
    assert not field.is_choice


def test_radio_button(form):
    fields = form.acroform.get_fields_with_qualified_name('Group4')
    assert len(fields) == 1 # 1 group, but not the 2 individual radio buttons
    field = fields[0]
    assert field.fully_qualified_name == 'Group4'
    assert field.is_top_level
    assert not field.is_text
    assert not field.is_checkbox
    assert field.is_radio_button
    assert not field.is_pushbutton
    assert not field.is_choice


def test_remove_fields(form):
    acro = form.acroform
    fields = acro.get_fields_with_qualified_name('Button2')
    assert len(fields) == 1
    acro.remove_fields(fields)
    fields = acro.get_fields_with_qualified_name('Button2')
    assert len(fields) == 0



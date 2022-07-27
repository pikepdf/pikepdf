# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MIT

"""Use pikepdf to find links in a PDF."""

from __future__ import annotations

import argparse

import pikepdf

Name = pikepdf.Name

parser = argparse.ArgumentParser(description="Find URIs in a PDF")
parser.add_argument('input_file')


def check_action(action):
    if action.Type != Name.Action:
        return
    if action.S == Name.URI:
        yield str(bytes(action.URI), encoding='ascii')


def check_object_aa(obj):
    if Name.AA in obj:
        for _name, action in obj.AA.items():
            yield from check_action(action)


def check_page_annots(page):
    if Name.Annots not in page:
        return
    annots = page.Annots
    for annot in annots:
        if annot.Type != Name.Annot:
            continue
        if annot.Subtype == Name.Link:
            link_annot = annot
            if Name.A in link_annot:
                action = link_annot.A
                yield from check_action(action)
        yield from check_object_aa(annot)


def check_page(page):
    yield from check_object_aa(page)


def gather_links(pdf):
    for page in pdf.pages:
        yield from check_page(page)
        yield from check_page_annots(page)


def main():
    args = parser.parse_args()
    with pikepdf.open(args.input_file) as pdf:
        links = gather_links(pdf)
        for link in links:
            print(link)


if __name__ == "__main__":
    main()

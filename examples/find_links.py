# Copyright (c) 2019, James R. Barlow

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Use pikepdf to find links in a PDF"""

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
    pdf = pikepdf.open(args.input_file)
    links = gather_links(pdf)
    for link in links:
        print(link)


if __name__ == "__main__":
    main()

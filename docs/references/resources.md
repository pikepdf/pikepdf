# Resources

- [qpdf manual]
- [PDF 1.7] ISO Specification PDF 32000-1:2008
- [Adobe Supplement to ISO 32000 BaseVersion 1.7 ExtensionLevel 3], Adobe Acrobat 9.0, June 2008, for AESv3
- Other [Adobe extensions] to the PDF specification

For information about copyrights and licenses, including those associated with the
images in this documentation, see the source tree file `REUSE.toml`.

pikepdf binary wheels also contain compiled third-party libraries (qpdf,
libjpeg-turbo, and depending on the platform OpenSSL, zlib, or the GnuTLS
stack). Their attribution and license mapping is in `third-party-licenses/` in
the source tree, and is redistributed inside every wheel under
`pikepdf-<version>.dist-info/licenses/`.

[adobe extensions]: https://www.adobe.com/devnet/pdf/pdf_reference.html
[adobe supplement to iso 32000 baseversion 1.7 extensionlevel 3]: https://www.adobe.com/content/dam/acom/en/devnet/pdf/adobe_supplement_iso32000.pdf
[pdf 1.7]: https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf
[qpdf manual]: https://qpdf.readthedocs.io/

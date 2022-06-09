v1.19.4
=======

-  Modify project settings to declare no support for Python 3.9 in pikepdf 1.x.
   pybind11 upstream has indicated there are stability problems when pybind11
   2.5 (used by pikepdf 1.x) is used with Python 3.9. As such, we are marking
   Python 3.9 as unsupported by pikepdf 1.x. Python 3.9 users should switch to
   pikepdf 2.x.

v1.19.3
=======

-  Fixed an exception that occurred when building the documentation, introduced in
   the previous release.

v1.19.2
=======

-  Fixed an exception with setting metadata objects to unsupported RDF types.
   Instead we make a best effort to convert to an appropriate type.
-  Prevent creating certain illegal dictionary key names.
-  Document procedure to remove an image.

v1.19.1
=======

-  Fixed an issue with ``unparse_content_stream``: we now assume the second item
   of each step in the content stream is an ``Operator``.
-  Fixed an issue with unparsing inline images.

v1.19.0
=======

-  Learned how to export CCITT images from PDFs that have ICC profiles attached.
-  Cherry-picked a workaround to a possible use-after-free caused by pybind11
   (pybind11 PR 2223).
-  Improved test coverage of code that handles inline images.

v1.18.0
=======

-  You can now use ``pikepdf.open(...allow_overwriting_input=True)`` to allow
   overwriting the input file, which was previously forbidden because it can corrupt
   data. This is accomplished safely by loading the entire PDF into memory at the
   time it is opened rather than loading content as needed. The option is disabled by
   default, to avoid a performance hit.
-  Prevent setup.py from creating junk temporary files (finally!)

v1.17.3
=======

-  Fixed crash when ``pikepdf.Pdf`` objects are used inside generators (:issue:`114`) and
   not freed or closed before the generator exits.

v1.17.2
=======

-  Fixed issue, "seek of closed file" where JBIG2 image data could not be accessed
   (only metadata could be) when a JBIG2 was extracted from a PDF.

v1.17.1
=======

-  Fixed building against the oldest supported version of QPDF (8.4.2), and
   configure CI to test against the oldest version. (:issue:`109`)

v1.17.0
=======

-  Fixed a failure to extract PDF images, where the image had both a palette
   and colorspace set to an ICC profile. The iamge is now extracted with the
   profile embedded. (:issue:`108`)
-  Added opt-in support for memory-mapped file access, using
   ``pikepdf.open(...access_mode=pikepdf.AccessMode.mmap)``. Memory mapping
   file access performance considerably, but may make application exception
   handling more difficult.

v1.16.1
=======

-  Fixed an issue with JBIG2 extraction, where the version number of the jbig2dec
   software may be written to standard output as a side effect. This could
   interfere with test cases or software that expects pikepdf to be stdout-clean.
-  Fixed an error that occurred when updating DocumentInfo to match XMP metadata,
   when XMP metadata had unexpected empty tags.
-  Fixed setup.py to better support Python 3.8 and 3.9.
-  Documentation updates.

v1.16.0
=======

-  Added support for extracting JBIG2 images with the image API. JBIG2 images are
   converted to ``PIL.Image``. Requires a JBIG2 decoder such as jbig2dec.
-  Python 3.5 support is deprecated and will end when Python 3.5 itself reaches
   end of life, in September 2020. At the moment, some tests are skipped on Python
   3.5 because they depend on Python 3.6.
-  Python 3.9beta is supported and is known to work on Fedora 33.

v1.15.1
=======

-  Fixed a regression - ``Pdf.save(filename)`` may hold file handles open after
   the file is fully written.
-  Documentation updates.

v1.15.0
=======

-  Fixed an issue where ``Decimal`` objects of precision exceeding the
   PDF specification could be written to output files, causing some PDF viewers,
   notably Acrobat, to parse the file incorrectly. We now limit precision to
   15 digits, which ought to be enough to prevent rounding error and parsing
   errors.
-  We now refuse to create pikepdf objects from ``float`` or ``Decimal`` that are
   ``NaN`` or ``±Infinity``. These concepts have no equivalent in PDF.
-  ``pikepdf.Array`` objects now implement ``.append()`` and ``.extend()`` with
   familiar Python ``list`` semantics, making them easier to edit.

v1.14.0
=======

-  Allowed use of ``.keys()``, ``.items()`` on ``pikepdf.Stream`` objects.
-  We now warn on attempts to modify ``pikepdf.Stream.Length``, which pikepdf will
   manage on its own when the stream is serialized. In the future attempting to
   change it will become an error.
-  Clarified documentation in some areas about behavior of ``pikepdf.Stream``.

v1.13.0
=======

-  Added support for editing PDF Outlines (also known as bookmarks or the table of
   contents). Many thanks to Matthias Erll for this contribution.
-  Added support for decoding run length encoded images.
-  ``Object.read_bytes()`` and ``Object.get_stream_buffer()`` can now request decoding
   of uncommon PDF filters.
-  Fixed test suite warnings related to pytest and hypothesis.
-  Fixed build on Cygwin. Thanks to @jhgarrison for report and testing.

v1.12.0
=======

-  Microsoft Visual C++ Runtime libraries are now included in the pikepdf Windows
   wheel, to improve ease of use on Windows.
-  Defensive code added to prevent using ``.emplace()`` on objects from a
   foreign PDF without first copying the object. Previously, this would raise
   an exception when the file was saved.

v1.11.2
=======

-  Fix "error caused by missing str function of Array" (:issue:`100,101`).
-  Lots of delinting and minor fixes.

v1.11.1
=======

-  We now avoid creating an empty XMP metadata entry when files are saved.
-  Updated documentation to describe how to delete the document information
   dictionary.

v1.11.0
=======

-  Prevent creation of dictionaries with invalid names (not beginning with ``/``).
-  Allow pikepdf's build to specify a qpdf source tree, allowing one to compile
   pikepdf against an unreleased/modified version of qpdf.
-  Improved behavior of ``pages.p()`` and ``pages.remove()`` when invalid parameters
   were given.
-  Fixed compatibility with libqpdf version 10.0.1, and build official wheels
   against this version.
-  Fixed compatibility with pytest 5.x.
-  Fixed the documentation build.
-  Fixed an issue with running tests in a non-Unicode locale.
-  Fixed a test that randomly failed due to a "deadline error".
-  Removed a possibly nonfree test file.

v1.10.4
=======

-  Rebuild Python wheels with newer version of libqpdf. Fixes problems with
   opening certain password-protected files (:issue:`87`).

v1.10.3
=======

-  Fixed ``isinstance(obj, pikepdf.Operator)`` not working. (:issue:`86`)
-  Documentation updates.

v1.10.2
=======

-  Fixed an issue where pages added from a foreign PDF were added as references
   rather than copies. (:issue:`80`)
-  Documentation updates.

v1.10.1
=======

-  Fixed build reproducibility (thanks to @lamby)
-  Fixed a broken link in documentation (thanks to @maxwell-k)

v1.10.0
=======

-  Further attempts to recover malformed XMP packets.
-  Added missing functionality to extract 1-bit palette images from PDFs.

v1.9.0
======

-  Improved a few cases of malformed XMP recovery.
-  Added an ``unparse_content_stream`` API to assist with converting the previously
   parsed content streams back to binary.

v1.8.3
======

-  If the XMP metadata packet is not well-formed and we are confident that it
   is essentially empty apart from XML fluff, we fix the problem instead of
   raising an exception.

v1.8.2
======

-  Fixed an issue where QPDF 8.4.2 would report different errors from QPDF 9.0.0,
   causing a test to fail. (:issue:`71`)

v1.8.1
======

-  Fixed an issue where files opened by name may not be closed correctly. Regression
   from v1.8.0.
-  Fixed test for readable/seekable streams evaluated to always true.

v1.8.0
======

-  Added API/property to iterate all objects in a PDF: ``pikepdf.Pdf.objects``.
-  Added ``pikepdf.Pdf.check()``, to check for problems in the PDF and return a
   text description of these problems, similar to ``qpdf --check``.
-  Improved internal method for opening files so that the code is smaller and
   more portable.
-  Added missing licenses to account for other binaries that may be included in
   Python wheels.
-  Minor internal fixes and improvements to the continuous integration scripts.

v1.7.1
======

-  This release was incorrectly marked as a patch-level release when it actually
   introduced one minor new feature. It includes the API change to support
   ``pikepdf.Pdf.objects``.

v1.7.0
======

-  Shallow object copy with ``copy.copy(pikepdf.Object)`` is now supported. (Deep
   copy is not yet supported.)
-  Support for building on C++11 has been removed. A C++14 compiler is now required.
-  pikepdf now generates manylinux2010 wheels on Linux.
-  Build and deploy infrastructure migrated to Azure Pipelines.
-  All wheels are now available for Python 3.5 through 3.8.

v1.6.5
======

-  Fixed build settings to support Python 3.8 on macOS and Linux. Windows support
   for Python 3.8 is not currently tested since continuous integration providers
   have not updated to Python 3.8 yet.
-  pybind11 2.4.3 is now required, to support Python 3.8.

v1.6.4
======

-  When images were encoded with CCITTFaxDecode, type G4, with the /EncodedByteAlign
   set to true (not default), the image extracted by pikepdf would be a corrupted
   form of the original, usually appearing as a small speckling of black pixels at the
   top of the page. Saving an image with pikepdf was not affected; this problem
   only occurred when attempting to extract images. We now refuse to extract images
   with these parameters, as there is not sufficient documentation to determine
   how to extract them. This image format is relatively rare.

v1.6.3
======

-  Fixed compatibility with libqpdf 9.0.0.

   -  A new method introduced in libqpdf 9.0.0 overloaded an older method, making
      a reference to this method in pikepdf ambiguous.

   -  A test relied on libqpdf raising an exception when a pikepdf user called
      ``Pdf.save(..., min_version='invalid')``. libqpdf no longer raises an
      exception in this situation, but ignores the invalid version. In the interest
      of supporting both versions, we defer to libqpdf. The failing test is
      removed, and documentation updated.

-  Several warnings, most specific to the Visual C++ compiler, were fixed.
-  The Windows CI scripts were adjusted for the change in libqpdf ABI version.
-  Wheels are now built against libqpdf 9.0.0.
-  libqpdf 8.4.2 and 9.0.0 are both supported.

v1.6.2
======

-  Fixed another build problem on Alpine Linux - musl-libc defines ``struct FILE``
   as an incomplete type, which breaks pybind11 metaprogramming that attempts
   to reason about the type.
-  Documentation improved to mention FreeBSD port.

v1.6.1
======

-  Dropped our one usage of QPDF's C API so that we use only C++.
-  Documentation improvements.

v1.6.0
======

-  Added bindings for QPDF's page object helpers and token filters. These
   enable: filtering content streams, capturing pages as Form XObjects, more
   convenient manipulation of page boxes.
-  Fixed a logic error on attempting to save a PDF created in memory in a
   way that overwrites an existing file.
-  Fixed ``Pdf.get_warnings()`` failed with an exception when attempting to
   return a warning or exception.
-  Improved manylinux1 binary wheels to compile all dependencies from source
   rather than using older versions.
-  More tests and more coverage.
-  libqpdf 8.4.2 is required.

v1.5.0
======

-  Improved interpretation of images within PDFs that use an ICC colorspace.
   Where possible we embed the ICC profile when extracting the image, and
   profile access to the ICC profile.
-  Fixed saving PDFs with their existing encryption.
-  Fixed documentation to reflect the fact that saving a PDF without
   specifying encryption settings will remove encryption.
-  Added a test to prevent overwriting the input PDF since overwriting
   corrupts lazy loading.
-  ``Object.write(filters=, decode_parms=)`` now detects invalid parameters
   instead of writing invalid values to ``Filters`` and ``DecodeParms``.
-  We can now extract some images that had stacked compression, provided it
   is ``/FlateDecode``.
-  Add convenience function ``Object.wrap_in_array()``.

v1.4.0
======

-  Added support for saving encrypted PDFs. (Reading them has been supported
   for a long time.)
-  Added support for setting the PDF extension level as well as version.
-  Added support converting strings to and from PDFDocEncoding, by
   registering a ``"pdfdoc"`` codec.

v1.3.1
======

-  Updated pybind11 to v2.3.0, fixing a possible GIL deadlock when
   pikepdf objects were shared across threads. (:issue:`27`)
-  Fixed an issue where PDFs with valid XMP metadata but missing an
   element that is usually present would be rejected as malformed XMP.

v1.3.0
======

-  Remove dependency on ``defusedxml.lxml``, because this library is deprecated.
   In the absence of other options for XML hardening we have reverted to
   standard ``lxml``.
-  Fixed an issue where ``PdfImage.extract_to()`` would write a file in
   the wrong directory.
-  Eliminated an intermediate buffer that was used when saving to an IO
   stream (as opposed to a filename). We would previously write the
   entire output to a memory buffer and then write to the output buffer;
   we now write directly to the stream.
-  Added ``Object.emplace()`` as a workaround for when one wants to
   update a page without generating a new page object so that
   links/table of contents entries to the original page are preserved.
-  Improved documentation. Eliminated all ``arg0`` placeholder variable
   names, which appeared when the documentation generator could not read a
   C++ variable name.
-  Added ``PageList.remove(p=1)``, so that it is possible to remove
   pages using counting numbers.

v1.2.0
======

-  Implemented ``Pdf.close()`` and ``with``-block context manager, to
   allow Pdf objects to be closed without relying on ``del``.
-  ``PdfImage.extract_to()`` has a new keyword argument ``fileprefix=``,
   which to specify a filepath where an image should be extracted with
   pikepdf setting the appropriate file suffix. This simplifies the API
   for the most common case of extracting images to files.
-  Fixed an internal test that should have suppressed the extraction of
   JPEGs with a nonstandard ColorTransform parameter set. Without the
   proper color transform applied, the extracted JPEGs will typically
   look very pink. Now, these images should fail to extract as was
   intended.
-  Fixed that ``Pdf.save(object_stream_mode=...)`` was ignored if the
   default ``fix_metadata_version=True`` was also set.
-  Data from one ``Pdf`` is now copied to other ``Pdf`` objects
   immediately, instead of creating a reference that required source
   PDFs to remain available. ``Pdf`` objects no longer reference each
   other.
-  libqpdf 8.4.0 is now required
-  Various documentation improvements

v1.1.0
======

-  Added workaround for macOS/clang build problem of the wrong exception
   type being thrown in some cases.
-  Improved translation of certain system errors to their Python
   equivalents.
-  Fixed issues resulting from platform differences in
   ``datetime.strftime``. (:issue:`25`)
-  Added ``Pdf.new``, ``Pdf.add_blank_page`` and ``Pdf.make_stream``
   convenience methods for creating new PDFs from scratch.
-  Added binding for new QPDF JSON feature: ``Object.to_json``.
-  We now automatically update the XMP PDFVersion metadata field to be
   consistent with the PDF's declared version, if the field is present.
-  Made our Python-augmented C++ classes easier for Python code
   inspectors to understand.
-  Eliminated use of the ``imghdr`` library.
-  Autoformatted Python code with black.
-  Fixed handling of XMP metadata that omits the standard
   ``<x:xmpmeta>`` wrapper.

v1.0.5
======

-  Fixed an issue where an invalid date in XMP metadata would cause an
   exception when updating DocumentInfo. For now, we warn that some
   DocumentInfo is not convertible. (In the future, we should also check
   if the XMP date is valid, because it probably is not.)
-  Rebuilt the binary wheels with libqpdf 8.3.0. libqpdf 8.2.1 is still
   supported.

v1.0.4
======

-  Updates to tests/resources (provenance of one test file, replaced
   another test file with a synthetic one)

v1.0.3
======

-  Fixed regression on negative indexing of pages.

v1.0.2
======

-  Fixed an issue where invalid values such as out of range years (e.g.
   1) in DocumentInfo would raise exceptions when using DocumentInfo to
   populate XMP metadata with ``.load_from_docinfo``.

v1.0.1
======

-  Fixed an exception with handling metadata that contains the invalid
   XML entity ``&#0;`` (an escaped NUL)

v1.0.0
======

-  Changed version to 1.0.

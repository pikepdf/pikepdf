.. _changelog:

Release notes
#############

.. figure:: images/pike-release.jpg
    :figwidth: 30%
    :alt: pike fish being released to water
    :align: right

    Releasing a pike.

pikepdf releases use the `semantic versioning <https://semver.org>`__
policy.

The pikepdf API (as provided by ``import pikepdf``) is stable and
is in production use. Note that the C++ extension module
``pikepdf._qpdf`` is a private interface within pikepdf that applications
should not access directly, along with any modules with a prefixed underscore.

Upcoming deprecations in v2.0.0
-------------------------------

-  Support for QPDF <= 10.0.1 will be dropped.
-  Support for Python 3.5 will be dropped when Python 3.5 reaches end of life,
   on 2020-09-13.
-  Support for macOS High Sierra (10.13 or older) will be dropped.

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

-  Fixed crash when ``pikepdf.Pdf`` objects are used inside generators (#114) and
   not freed or closed before the generator exits.

v1.17.2
=======

-  Fixed issue, "seek of closed file" where JBIG2 image data could not be accessed
   (only metadata could be) when a JBIG2 was extracted from a PDF.

v1.17.1
=======

-  Fixed building against the oldest supported version of QPDF (8.4.2), and
   configure CI to test against the oldest version. (#109)

v1.17.0
=======

-  Fixed a failure to extract PDF images, where the image had both a palette
   and colorspace set to an ICC profile. The iamge is now extracted with the
   profile embedded. (#108)
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

-  Fix "error caused by missing str function of Array" (#100, #101).
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
   opening certain password-protected files (#87).

v1.10.3
=======

-  Fixed ``isinstance(obj, pikepdf.Operator)`` not working. (#86)
-  Documentation updates.

v1.10.2
=======

-  Fixed an issue where pages added from a foreign PDF were added as references
   rather than copies. (#80)
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
   causing a test to fail. (#71)

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
   pikepdf objects were shared across threads. (#27)
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
   ``datetime.strftime``. (#25)
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
   0) in DocumentInfo would raise exceptions when using DocumentInfo to
   populate XMP metadata with ``.load_from_docinfo``.

v1.0.1
======

-  Fixed an exception with handling metadata that contains the invalid
   XML entity ``&#0;`` (an escaped NUL)

v1.0.0
======

-  Changed version to 1.0.

v0.10.2
=======

Fixes
-----

-  Fixed segfault when overwriting the pikepdf file that is currently
   open on Linux.
-  Fixed removal of an attribute metadata value when values were present
   on the same node.

v0.10.1
=======

.. _fixes-1:

Fixes
-----

-  Avoid canonical XML since it is apparently too strict for XMP.

v0.10.0
=======

.. _fixes-2:

Fixes
-----

-  Fixed several issues related to generating XMP metadata that passed
   veraPDF validation.
-  Fixed a random test suite failure for very large negative integers.
-  The lxml library is now required.

v0.9.2
======

.. _fixes-3:

Fixes
-----

-  Added all of the commonly used XML namespaces to XMP metadata
   handling, so we are less likely to name something 'ns1', etc.
-  Skip a test that fails on Windows.
-  Fixed build errors in documentation.

v0.9.1
======

.. _fixes-4:

Fixes
-----

-  Fix ``Object.write()`` accepting positional arguments it wouldn't use
-  Fix handling of XMP data with timezones (or missing timezone
   information) in a few cases
-  Fix generation of XMP with invalid XML characters if the invalid
   characters were inside a non-scalar object

v0.9.0
======

Updates
-------

-  New API to access and edit PDF metadata and make consistent edits to
   the new and old style of PDF metadata.
-  32-bit binary wheels are now available for Windows
-  PDFs can now be saved in QPDF's "qdf" mode
-  The Python package defusedxml is now required
-  The Python package python-xmp-toolkit and its dependency libexempi
   are suggested for testing, but not required

.. _fixes-5:

Fixes
-----

-  Fixed handling of filenames that contain multibyte characters on
   non-UTF-8 systems

Breaking
--------

-  The ``Pdf.metadata`` property was removed, and replaced with the new
   metadata API
-  ``Pdf.attach()`` has been removed, because the interface as
   implemented had no way to deal with existing attachments.

v0.3.7
======

-  Add API for inline images to unparse themselves

v0.3.6
======

-  Performance of reading files from memory improved to avoid
   unnecessary copies.
-  It is finally possible to use ``for key in pdfobj`` to iterate
   contents of PDF Dictionary, Stream and Array objects. Generally these
   objects behave more like Python containers should now.
-  Package API declared beta.

v0.3.5
======

.. _breaking-1:

Breaking
--------

-  ``Pdf.save(...stream_data_mode=...)`` has been dropped in favor of
   the newer ``compress_streams=`` and ``stream_decode_level``
   parameters.

.. _fixes-6:

Fixes
-----

-  A use-after-free memory error that caused occasional segfaults and
   "QPDFFakeName" errors when opening from stream objects has been
   resolved.

v0.3.4
======

.. _updates-1:

Updates
-------

-  pybind11 vendoring has ended now that v2.2.4 has been released

v0.3.3
======

.. _breaking-2:

Breaking
--------

-  libqpdf 8.2.1 is now required

.. _updates-2:

Updates
-------

-  Improved support for working with JPEG2000 images in PDFs
-  Added progress callback for saving files,
   ``Pdf.save(..., progress=)``
-  Updated pybind11 subtree

.. _fixes-7:

Fixes
-----

-  ``del obj.AttributeName`` was not implemented. The attribute
   interface is now consistent
-  Deleting named attributes now defers to the attribute dictionary for
   Stream objects, as get/set do
-  Fixed handling of JPEG2000 images where metadata must be retrieved
   from the file

v0.3.2
======

.. _updates-3:

Updates
-------

-  Added support for direct image extraction of CMYK and grayscale
   JPEGs, where previously only RGB (internally YUV) was supported
-  ``Array()`` now creates an empty array properly
-  The syntax ``Name.Foo in Dictionary()``, e.g.
   ``Name.XObject in page.Resources``, now works

v0.3.1
======

.. _breaking-3:

Breaking
--------

-  ``pikepdf.open`` now validates its keyword arguments properly,
   potentially breaking code that passed invalid arguments
-  libqpdf 8.1.0 is now required - libqpdf 8.1.0 API is now used for
   creating Unicode strings
-  If a non-existent file is opened with ``pikepdf.open``, a
   ``FileNotFoundError`` is raised instead of a generic error
-  We are now *temporarily* vendoring a copy of pybind11 since its
   master branch contains unreleased and important fixes for Python 3.7.

.. _updates-4:

Updates
-------

-  The syntax ``Name.Thing`` (e.g. ``Name.DecodeParms``) is now
   supported as equivalent to ``Name('/Thing')`` and is the recommended
   way to refer names within a PDF
-  New API ``Pdf.remove_unneeded_resources()`` which removes objects
   from each page's resource dictionary that are not used in the page.
   This can be used to create smaller files.

.. _fixes-8:

Fixes
-----

-  Fixed an error parsing inline images that have masks
-  Fixed several instances of catching C++ exceptions by value instead
   of by reference

v0.3.0
======

.. _breaking-4:

Breaking
--------

-  Modified ``Object.write`` method signature to require ``filter`` and
   ``decode_parms`` as keyword arguments
-  Implement automatic type conversion from the PDF Null type to
   ``None``
-  Removed ``Object.unparse_resolved`` in favor of
   ``Object.unparse(resolved=True)``
-  libqpdf 8.0.2 is now required at minimum

.. _updates-5:

Updates
-------

-  Improved IPython/Jupyter interface to directly export temporary PDFs
-  Updated to qpdf 8.1.0 in wheels
-  Added Python 3.7 support for Windows
-  Added a number of missing options from QPDF to ``Pdf.open`` and
   ``Pdf.save``
-  Added ability to delete a slice of pages
-  Began using Jupyter notebooks for documentation

v0.2.2
======

-  Added Python 3.7 support to build and test (not yet available for
   Windows, due to lack of availability on Appveyor)
-  Removed setter API from ``PdfImage`` because it never worked anyway
-  Improved handling of ``PdfImage`` with trivial palettes

v0.2.1
======

-  ``Object.check_owner`` renamed to ``Object.is_owned_by``
-  ``Object.objgen`` and ``Object.get_object_id`` are now public
   functions
-  Major internal reorganization with ``pikepdf.models`` becoming the
   submodule that holds support code to ease access to PDF objects as
   opposed to wrapping QPDF.

v0.2.0
======

-  Implemented automatic type conversion for ``int``, ``bool`` and
   ``Decimal``, eliminating the ``pikepdf.{Integer,Boolean,Real}``
   types. Removed a lot of associated numerical code.

Everything before v0.2.0 can be considered too old to document.

#!/bin/bash
set -ex
python -m pip install --upgrade pip
export CIBW_BEFORE_BUILD='pip install pybind11'
export CIBW_ENVIRONMENT='INCLUDE="$INCLUDE;c:\\qpdf\\include" LIB="$LIB;c:\\qpdf\\lib" LIBPATH="$LIBPATH;c:\\qpdf\\lib"'
pip install cibuildwheel==$CIBUILDWHEEL_VERSION
cibuildwheel --output-dir wheelhouse .

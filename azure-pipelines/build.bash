#!/bin/bash
set -ex
python -m pip install --upgrade pip
pip install cibuildwheel==$CIBUILDWHEEL_VERSION
cibuildwheel --output-dir wheelhouse .

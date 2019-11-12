#!/bin/bash
set -ex
python -m pip install --upgrade pip
pip install cibuildwheel==$CIBUILDWHEEL_VERSION || \
    pip install git+git://github.com/joerick/cibuildwheel.git@$CIBUILDWHEEL_VERSION
cibuildwheel --output-dir wheelhouse .

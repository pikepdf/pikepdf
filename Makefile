# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
# This is really just for testing

.PHONY:
all: build

.PHONY: invalidate-cppcov
invalidate-cppcov:
	find . -name "*.gcno" -delete

# Use 'uv pip', not bare 'pip'. The venv ships an old pip (22.0.x) that does not
# reliably recompile the scikit-build-core editable extension: repeated
# `pip install -e .` reuses a stale build and silently drops C++ changes. uv
# builds the editable wheel correctly every time.
.PHONY: build
build: invalidate-cppcov
	uv pip install --no-build-isolation -e .

.PHONY: pip-install-e
pip-install-e: invalidate-cppcov
	uv pip install -e .

.PHONY: clean-coverage-pycov
clean-coverage-pycov:
	rm -rf coverage/pycov
	rm -f .coverage

.PHONY: clean-coverage-cppcov
clean-coverage-cppcov:
	rm -rf coverage/cppcov
	find . -name "*.gcda" -delete
	rm -f coverage/cpp.info

.PHONY: clean-coverage
clean-coverage: clean-coverage-cppcov clean-coverage-pycov

.PHONY: clean
clean: clean-coverage
	rm -rf build/
	rm -f src/pikepdf/_core.*so

.PHONY: test
test: build
	pytest -n auto

.PHONY: pycov
pycov: clean-coverage-pycov
	pytest --cov-report html --cov=src -n auto

.PHONY: build-cppcov
build-cppcov:
	SKBUILD_BUILD_DIR=build/coverage \
	  CMAKE_ARGS="-DCMAKE_CXX_FLAGS=--coverage -DCMAKE_SHARED_LINKER_FLAGS=--coverage" \
	  pip install --no-build-isolation -e .

coverage/cpp.info: clean-coverage-cppcov build-cppcov pycov
	lcov --capture --directory build/coverage --output-file coverage/cppall.info
	lcov --extract coverage/cppall.info '*/src/core/*' -o coverage/cpp.info

coverage/cppcov: coverage/cpp.info
	-mkdir -p coverage/cppcov
	genhtml coverage/cpp.info --output-directory coverage/cppcov

.PHONY: cppcov
cppcov: clean-coverage-cppcov build-cppcov pycov coverage/cppcov

.PHONY: coverage
coverage: cppcov pycov

.PHONY: docs
docs: build
	$(MAKE) -C docs clean
	$(MAKE) -C docs html doctest
	rm -f docs/doc.log.txt

cibuildwheel-test: clean-coverage
	rm -rf build/bdist.* build/lib.* build/temp.*
	pipx run cibuildwheel --platform linux
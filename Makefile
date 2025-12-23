# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
# This is really just for testing

.PHONY:
all: build

.PHONY: invalidate-cppcov
invalidate-cppcov:
	find . -name "*.gcno" -delete

.PHONY: build
build: invalidate-cppcov
	python -m pip install --no-build-isolation -e .

.PHONY: pip-install-e
pip-install-e: invalidate-cppcov
	python -m pip install -e .

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
	rm -rf build builddir
	rm -f src/pikepdf/_core*.so

.PHONY: test
test: build
	pytest -n auto

.PHONY: pycov
pycov: clean-coverage-pycov
	pytest --cov-report html --cov=src -n auto

.PHONY: build-cppcov
build-cppcov:
	meson setup builddir-cov -Db_coverage=true --wipe || meson setup builddir-cov -Db_coverage=true
	meson compile -C builddir-cov
	cp builddir-cov/src/core/_core*.so src/pikepdf/

# For coverage, we need to bypass the meson-python editable loader and use src/ directly
.PHONY: pycov-cppcov
pycov-cppcov: clean-coverage-pycov
	-pip uninstall -y pikepdf
	PYTHONPATH=src LD_LIBRARY_PATH="$(shell dirname $(shell readlink -f ../qpdf/build/libqpdf/libqpdf.so 2>/dev/null || echo /usr/local/lib)):$$LD_LIBRARY_PATH" \
		pytest --cov-report html --cov=src -n auto

coverage/cpp.info: clean-coverage-cppcov build-cppcov pycov-cppcov
	lcov --capture --directory builddir-cov --output-file coverage/cppall.info
	lcov --extract coverage/cppall.info '*/src/core/*' -o coverage/cpp.info

coverage/cppcov: coverage/cpp.info
	-mkdir -p coverage/cppcov
	genhtml coverage/cpp.info --output-directory coverage/cppcov

.PHONY: cppcov
cppcov: clean-coverage-cppcov build-cppcov pycov-cppcov coverage/cppcov

.PHONY: coverage
coverage: cppcov

.PHONY: docs
docs: build
	$(MAKE) -C docs clean
	$(MAKE) -C docs html doctest
	rm -f docs/doc.log.txt

cibuildwheel-test: clean-coverage
	rm -rf build builddir
	pipx run cibuildwheel --platform linux
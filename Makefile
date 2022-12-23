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
	python setup.py build_ext --inplace

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
	python setup.py clean --all
	rm -f src/pikepdf/_core.*so

.PHONY: test
test: build
	pytest -n auto

# Reminder to not indent if clauses, because Makefile...
ifdef SETUPTOOLS_SCM_PRETEND_VERSION
$(info Using version from SETUPTOOLS_SCM_PRETEND_VERSION ${SETUPTOOLS_SCM_PRETEND_VERSION})
version := ${SETUPTOOLS_SCM_PRETEND_VERSION}
else
$(info Using version from git describe)
version := $(subst v,,$(shell git describe --tags))
endif

ifndef MACOSX_DEPLOYMENT_TARGET
$(info Setting MACOSX_DEPLOYMENT_TARGET to default of 11.0)
MACOSX_DEPLOYMENT_TARGET=11.0
endif
underscored_target := $(subst .,_,${MACOSX_DEPLOYMENT_TARGET})
$(info $$underscored_target is ${underscored_target})

$(info Version of wheels will be: ${version})
macwheel39 := pikepdf-$(version)-cp39-cp39-macosx_${underscored_target}_arm64.whl
macwheel310 := pikepdf-$(version)-cp310-cp310-macosx_${underscored_target}_arm64.whl
$(info $$macwheel39 is ${macwheel39})
$(info $$macwheel310 is ${macwheel310})

wheelhouse/$(macwheel39): clean
	rm -f wheelhouse/pikepdf*cp39*.whl
	rm -rf .venv39
	/opt/homebrew/bin/python3.9 -m venv .venv39
	( \
		source .venv39/bin/activate; \
		python -m pip install --upgrade setuptools pip wheel; \
		python -m pip install .; \
		python -m pip wheel -w wheelhouse .; \
	)
	mv wheelhouse/pikepdf*cp39*.whl wheelhouse/$(macwheel39)

	# rm -rf unpacked/
	# python -m wheel unpack wheelhouse/$(macwheel39) --dest unpacked
	# rm -f wheelhouse/$(macwheel39)
	# install_name_tool -change /usr/local/lib/libqpdf.28.dylib \
	# 	/Users/jb/src/qpdf/libqpdf/build/.libs/libqpdf.28.dylib \
	# 	unpacked/pikepdf-*/pikepdf/_core.cpython*.so
	# python -m wheel pack unpacked/pikepdf-*/ --dest-dir wheelhouse
	# rm -rf unpacked/


wheelhouse/$(macwheel310): clean
	rm -f wheelhouse/pikepdf*cp310*.whl
	rm -rf .venv310
	/opt/homebrew/opt/python@3.10/bin/python3.10 -m venv .venv310
	( \
		source .venv310/bin/activate; \
		python -m pip install --upgrade setuptools pip wheel; \
		python -m pip install .; \
		python -m pip wheel -w wheelhouse .; \
	)
	mv wheelhouse/pikepdf*cp310*.whl wheelhouse/$(macwheel310)

	# rm -rf unpacked/
	# python -m wheel unpack wheelhouse/$(macwheel310) --dest unpacked
	# rm -f wheelhouse/$(macwheel310)
	# install_name_tool -change /usr/local/lib/libqpdf.28.dylib \
	# 	/Users/jb/src/qpdf/libqpdf/build/.libs/libqpdf.28.dylib \
	# 	unpacked/pikepdf-*/pikepdf/_core.cpython*.so
	# python -m wheel pack unpacked/pikepdf-*/ --dest-dir wheelhouse
	# rm -rf unpacked/

wheelhouse/delocated/$(macwheel39): wheelhouse/$(macwheel39)
	delocate-wheel -w wheelhouse/delocated -v wheelhouse/$(macwheel39)

wheelhouse/delocated/$(macwheel310): wheelhouse/$(macwheel310)
	delocate-wheel -w wheelhouse/delocated -v wheelhouse/$(macwheel310)

.PHONY: macwheel39
macwheel39: wheelhouse/delocated/$(macwheel39)
	-

.PHONY: macwheel310
macwheel310: wheelhouse/delocated/$(macwheel310)
	-

.PHONY: apple-silicon-wheels
apple-silicon-wheels: wheelhouse/delocated/$(macwheel39) wheelhouse/delocated/$(macwheel310)
	twine upload wheelhouse/delocated/$(macwheel39) wheelhouse/delocated/$(macwheel310)

.PHONY: pycov
pycov: clean-coverage-pycov
	pytest --cov-report html --cov=src -n auto

.PHONY: build-cppcov
build-cppcov:
	env CFLAGS="--coverage" python setup.py build_ext --inplace

coverage/cpp.info: clean-coverage-cppcov build-cppcov pycov
	lcov --no-external --capture --directory . --output-file coverage/cppall.info
	lcov --remove coverage/cppall.info '*/pybind11/*' -o coverage/cpp.info

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
	$(MAKE) -C docs html
	rm -f docs/doc.log.txt

cibuildwheel-test: clean-coverage
	rm -rf build/bdist.* build/lib.* build/temp.*
	cibuildwheel --platform linux
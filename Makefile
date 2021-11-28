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
	rm -f src/pikepdf/_qpdf.*so

.PHONY: test
test: build
	pytest -n auto

version := $(subst v,,$(shell git describe --tags))
macwheel39 := pikepdf-$(version)-cp39-cp39-macosx_11_0_arm64.whl
macwheel310 := pikepdf-$(version)-cp310-cp310-macosx_11_0_arm64.whl
#$(info $$version is [${version}])
#$(info $$macwheel is [${macwheel}])

wheelhouse/$(macwheel39): clean pip-install-e
	rm -f wheelhouse/pikepdf*cp39*.whl
	python -m pip wheel -w wheelhouse .
	mv wheelhouse/pikepdf*cp39*.whl wheelhouse/$(macwheel39)

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

wheelhouse/delocated/$(macwheel39): wheelhouse/$(macwheel39)
	delocate-wheel -w wheelhouse/delocated -v wheelhouse/$(macwheel39)

wheelhouse/delocated/$(macwheel310): wheelhouse/$(macwheel310)
	delocate-wheel -w wheelhouse/delocated -v wheelhouse/$(macwheel310)

.PHONY: apple-silicon-wheels
apple-silicon-wheels: wheelhouse/delocated/$(macwheel310) wheelhouse/delocated/$(macwheel39)
	echo twine upload wheelhouse/delocated/$(macwheel39) wheelhouse/delocated/$(macwheel310)

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
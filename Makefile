# This is really just for testing

.PHONY:
all: build

.PHONY: invalidate-cppcov
invalidate-cppcov:
	find . -name "*.gcno" -delete

.PHONY: build
build: invalidate-cppcov
	# python setup.py build_ext --inplace
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

.PHONY: test
test: build
	pytest -n auto

version := $(subst v,,$(shell git describe --tags))
macwheel := pikepdf-$(version)-cp39-cp39-macosx_11_0_arm64.whl
#$(info $$version is [${version}])
#$(info $$macwheel is [${macwheel}])

$(macwheel): clean build
	rm pikepdf*.whl
	python -m pip wheel .
	mv pikepdf*.whl $(macwheel)

fixed/$(macwheel): $(macwheel)
	delocate-wheel -w fixed -v $(macwheel)

.PHONY: apple-silicon-wheels
apple-silicon-wheels: fixed/$(macwheel)
	twine upload fixed/$(macwheel)

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

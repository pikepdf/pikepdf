# This is really just for testing

.PHONY: build coverage test all

build:
	python setup.py build_ext --inplace

all: build

clean: clean-coverage
	python setup.py clean --all

clean-coverage-pycov:
	rm -rf coverage/pycov
	rm -f .coverage

clean-coverage-cppcov:
	rm -rf coverage/cppcov
	find . -name "*.gcda" -o -name "*.gcno" -print0 | xargs -0 rm
	rm -f coverage/cpp.info

clean-coverage: clean-coverage-cppcov clean-coverage-pycov

test: build
	pytest -n auto

cppcov: clean-coverage-cppcov
	python setup.py clean --all
	env CFLAGS="-coverage" python setup.py build_ext --inplace
	pytest -n auto
	-mkdir -p coverage/cppcov
	lcov --capture --directory . --output-file coverage/cpp.info
	genhtml coverage/cpp.info --output-directory coverage/cppcov

pycov: clean-coverage-pycov
	pytest --cov-report html --cov=src -n auto

coverage: cppcov pycov

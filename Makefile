.PHONY: test fmt lint build

test:
	pytest -q

fmt:
	ruff check --fix

lint:
	ruff check

build:
	python -m build

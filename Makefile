# Developer shortcuts for the iEESBots governance core.
# Runtime package uses only the Python standard library.

PYTHON ?= python3
COV_ARGS := --cov=ieesbots --cov-branch --cov-report=term-missing

.PHONY: help test coverage demo json clean

help:
	@echo "Targets:"
	@echo "  make test      Run the test suite"
	@echo "  make coverage  Run tests with the 100% line+branch coverage gate"
	@echo "  make demo      Run the built-in synthetic demo case"
	@echo "  make json      Run the demo and print structured JSON"
	@echo "  make clean     Remove local test/coverage artifacts"

test:
	$(PYTHON) -m pytest -q

coverage:
	$(PYTHON) -m pytest $(COV_ARGS)

demo:
	$(PYTHON) -m ieesbots --demo

json:
	$(PYTHON) -m ieesbots --demo --json

clean:
	rm -rf .pytest_cache .coverage .coverage.* htmlcov coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +

.PHONY: help install install-dev format lint typecheck test coverage clean check

help:
	@echo "Available commands:"
	@echo "  install      Install runtime dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  format       Format code with black and isort"
	@echo "  lint         Run flake8 linting"
	@echo "  typecheck    Run mypy type checking"
	@echo "  test         Run tests"
	@echo "  coverage     Run tests with coverage report"
	@echo "  check        Run all quality checks (format, lint, typecheck, test)"
	@echo "  clean        Clean up generated files"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

format:
	black src/ tests/
	isort src/ tests/

lint:
	flake8 src/ tests/

typecheck:
	mypy src/

test:
	pytest --maxfail=1 -v

coverage:
	pytest --cov=src --cov-report=html --cov-report=term-missing

check: format lint typecheck test
	@echo "All checks passed!"

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
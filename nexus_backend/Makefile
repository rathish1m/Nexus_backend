.PHONY: help install test test-co	@echo "  docker-stop     - Stop Docker containers"


help:
	@echo " Available commands: "
	@echo "  install             - Install production dependencies"
	@echo "  install-dev         - Install development dependencies"
	@echo "  venv                - Create virtual environment"
	@echo "  test                - Run all tests"
	@echo "  test-cov            - Run tests with coverage"
	@echo "  test-cov-open       - Run tests with coverage and open HTML report"
	@echo "  test-e2e            - Run end-to-end browser tests (Playwright/Selenium)"
	@echo "  test-fast           - Run tests without coverage (faster)"
	@echo "  lint                - Run code linting"
	@echo "  format              - Format code with black and isort"
	@echo "  clean               - Clean up temporary files"
	@echo "  migrate             - Run database migrations"
	@echo "  makemigrations      - Create database migrations"
	@echo "  showmigrations      - Show migration status"
	@echo "  sqlmigrate          - Show SQL for a migration (app=your_app migration=0001)"
	@echo "  dbshell             - Open database shell"
	@echo "  create-db           - Create database"
	@echo "  setup-db            - Setup database with PostGIS support"
	@echo "  createsuperuser     - Create Django superuser"
	@echo "  reset-db            - Reset database (WARNING: destroys data)"
	@echo "  backup-db           - Backup database"
	@echo "  restore-db          - Restore database from backup"
	@echo "  static              - Collect and compress static files"
	@echo "  collectstatic       - Collect static files"
	@echo "  runserver           - Start development server"
	@echo "  shell               - Open Django shell"
	@echo "  celery-worker       - Start Celery worker"
	@echo "  celery-beat         - Start Celery beat scheduler"
	@echo "  flower              - Start Flower (Celery monitoring)"
	@echo "  docker-build        - Build Docker image"
	@echo "  docker-run          - Run Docker container"
	@echo "  docker-stop         - Stop Docker container"
	@echo "  check-security      - Run security checks"
	@echo "  check-deps          - Check for outdated dependencies"
	@echo "  update-deps         - Update dependencies"
	@echo "  pre-commit-install  - Install pre-commit hooks"
	@echo "  pre-commit-run      - Run pre-commit on all files"
	@echo "  pre-commit-run-all  - Run pre-commit on staged files"
	@echo "  i18n-audit          - Audit translation files coverage"
	@echo "  i18n-audit-json     - Audit translations with JSON output"
	@echo "  i18n-extract        - Extract strings for translation"
	@echo "  i18n-compile        - Compile translation files"
	@echo "  i18n-update         - Update translation files"
	@echo "  i18n-check          - Check translation coverage (CI-friendly)"
	@echo "  check-docs          - Validate documentation structure and i18n"
	@echo "  browse-docs         - Open documentation browser"
	@echo "  check-inventory     - Check inventory status"
	@echo "  check-duplicates    - Check for signal duplicates"
	@echo "  clean-duplicates    - Clean duplicate signals"
	@echo "  create-test-data    - Create test data for development"
	@echo "  demo-installation   - Run installation demo"
	@echo "  verify-photos       - Verify photo upload functionality"
	@echo "  analyze-workflow    - Analyze rejection workflow"
	@echo "  fix-billing         - Fix billing customers"
	@echo "  verify-billing      - Verify billing creation"


# Installation
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

venv:
	python3 -m venv venv
	@echo "Virtual environment created. Run 'source venv/bin/activate' to activate it."

# Testing
test:
	@bash scripts/run_tests.sh ./venv/bin/python -m pytest

test-cov:
	@bash scripts/run_tests.sh ./venv/bin/python -m pytest --cov=. --cov-report=html --cov-report=term || { \
		echo "Tests failed, but generating coverage report..."; \
		coverage combine 2>/dev/null || true; \
		coverage html; \
	}

test-cov-open:
	@bash scripts/run_tests.sh pytest --cov=. --cov-report=html --cov-report=term || { \
		echo "Tests failed, but generating coverage report..."; \
		coverage combine 2>/dev/null || true; \
		coverage html; \
	}
	@echo "Opening HTML coverage report..."
	@if command -v xdg-open >/dev/null 2>&1; then \
		xdg-open htmlcov/index.html; \
	elif command -v open >/dev/null 2>&1; then \
		open htmlcov/index.html; \
	else \
		echo "Open this file in your browser: $(PWD)/htmlcov/index.html"; \
	fi

coverage-open:
	@echo "Opening HTML coverage report..."
	@if command -v xdg-open >/dev/null 2>&1; then \
		xdg-open htmlcov/index.html; \
	elif command -v open >/dev/null 2>&1; then \
		open htmlcov/index.html; \
	else \
		echo "Open this file in your browser: $(PWD)/htmlcov/index.html"; \
	fi

test-fast:
	pytest -x --tb=short

test-e2e:
	@echo "Running end-to-end tests (Playwright/Selenium)..."
	pytest tests/e2e -m e2e -v

# Code Quality
lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

format:
	black .
	isort .

# Database
migrate:
	python manage.py migrate

makemigrations:
	python manage.py makemigrations

showmigrations:
	python manage.py showmigrations

sqlmigrate:
	@echo "Usage: make sqlmigrate app=your_app migration=0001"
	@if [ -z "$(app)" ] || [ -z "$(migration)" ]; then \
		echo "Error: Please specify app and migration parameters"; \
		echo "Example: make sqlmigrate app=main migration=0001"; \
		exit 1; \
	fi
	python manage.py sqlmigrate $(app) $(migration)

dbshell:
	python manage.py dbshell

create-db:
	python manage.py migrate --run-syncdb

setup-db:
	@echo "Setting up database with PostGIS support..."
	@echo "Creating PostGIS extension..."
	@psql -U postgres -h localhost -c "CREATE EXTENSION IF NOT EXISTS postgis;" nexus_db 2>/dev/null || echo "PostGIS extension created (or already exists)"
	@echo "Granting permissions to nexus_user..."
	@psql -U postgres -h localhost -c "GRANT ALL ON SCHEMA public TO nexus_user;" nexus_db 2>/dev/null || echo "Permissions granted (or already set)"
	@psql -U postgres -h localhost -c "ALTER USER nexus_user CREATEDB;" nexus_db 2>/dev/null || echo "CREATEDB privilege granted (or already set)"
	@echo "Running database migrations..."
	python manage.py migrate
	@echo "Database setup complete!"

createsuperuser:
	@echo "Creating Django superuser..."
	python manage.py createsuperuser --noinput || (echo "Interactive superuser creation:" && python manage.py createsuperuser)

reset-db:
	@echo "WARNING: This will destroy all data in the database!"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		python manage.py reset_db --noinput; \
		python manage.py migrate; \
		echo "Database reset complete."; \
	else \
		echo "Operation cancelled."; \
	fi

backup-db:
	@echo "Backing up database..."
	python manage.py dumpdata --exclude=contenttypes --exclude=auth.permission --exclude=sessions --exclude=admin.logentry --output=backup_$(shell date +%Y%m%d_%H%M%S).json --indent=2
	@echo "Backup created."

restore-db:
	@echo "Available backups:"
	@ls -la backup_*.json 2>/dev/null || echo "No backups found."
	@read -p "Enter backup filename: " filename; \
	if [ -f "$$filename" ]; then \
		python manage.py loaddata $$filename; \
		echo "Database restored from $$filename."; \
	else \
		echo "File $$filename not found."; \
	fi

# Static Files
static: collectstatic
	@echo "Checking for compressor tags..."
	@if rg -n "\{%\s*compress\s+(css|js)" templates 2>/dev/null || rg -n "\{%\s*compress\s+(css|js)" **/templates 2>/dev/null; then \
		echo "compress tags found; running compressor"; \
		python manage.py compress || (echo "compress failed" && exit 1); \
	else \
		echo "No {% compress %} tags found; skipping compressor"; \
	fi

collectstatic:
	python manage.py collectstatic --noinput

# Development Server
runserver:
	python manage.py runserver

shell:
	python manage.py shell

# Celery
celery-worker:
	celery -A nexus_backend worker --loglevel=info

celery-beat:
	celery -A nexus_backend beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

flower:
	celery -A nexus_backend flower

# Docker
docker-build:
	docker build -t nexus-backend .

docker-run:
	docker run -p 8000:8000 --env-file .env nexus-backend

docker-stop:
	docker stop $$(docker ps -q --filter ancestor=nexus-backend) || true

# Test DB (PostGIS) helpers
test-db-up:
	docker compose -f docker-compose.test.yml up -d

test-db-down:
	docker compose -f docker-compose.test.yml down

test-with-db:
	@echo "Starting test DB..."
	docker compose -f docker-compose.test.yml up -d
	@echo "Exporting DB env vars and running pytest against test DB"
	@export DATABASE_HOST=127.0.0.1; \
	export DATABASE_PORT=5433; \
	export DATABASE_USER=nexus_test; \
	export DATABASE_PASSWORD=secret; \
	export DATABASE_NAME=nexus_test; \
	PYTHONPATH=. DATABASE_HOST=$$DATABASE_HOST DATABASE_PORT=$$DATABASE_PORT \
	DATABASE_USER=$$DATABASE_USER DATABASE_PASSWORD=$$DATABASE_PASSWORD \
	DATABASE_NAME=$$DATABASE_NAME pytest -q


# Security & Maintenance
check-security:
	bandit -r .

check-deps:
	pip list --outdated

update-deps:
	pip install --upgrade -r requirements.txt
	pip install --upgrade -r requirements-dev.txt

# Pre-commit hooks
pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

pre-commit-run-all:
	pre-commit run

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.log" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/ .tox/
	rm -rf staticfiles/CACHE/

# Internationalization (i18n) management
i18n-audit:
	@echo "🌍 Running multilingual translation audit..."
	@./scripts/i18n-audit.sh

i18n-audit-json:
	@echo "🌍 Running translation audit with JSON output..."
	@./scripts/i18n-audit.sh --json

i18n-extract:
	@echo "📝 Extracting translatable strings..."
	@echo "Generating base template (English source)..."
	python manage.py makemessages --all --ignore=venv --ignore=node_modules
	@echo "Updating French translations..."
	python manage.py makemessages -l fr --ignore=venv --ignore=node_modules --update
	@echo "✅ Translation strings extracted"

i18n-compile:
	@echo "🔨 Compiling translation files..."
	python manage.py compilemessages
	@echo "✅ Translation files compiled"

i18n-update: i18n-extract i18n-compile
	@echo "🔄 Translation files updated and compiled"

i18n-check:
	@echo "🔍 Checking translation coverage for CI..."
	@./scripts/i18n-audit.sh --quiet --min-coverage 80

# Documentation validation
check-docs:
	@echo "📚 Validating documentation structure..."
	@python scripts/docs/check_docs_structure.py
	@python scripts/docs/check_i18n_compliance.py
	@python scripts/docs/check_filename_i18n.py
	@echo "✅ Documentation validation complete"

browse-docs:
	@echo "📖 Opening documentation browser..."
	@bash scripts/docs/browse_docs.sh

# Data management
check-inventory:
	@echo "📦 Checking inventory..."
	@python scripts/data/check_inventory.py

check-duplicates:
	@echo "🔍 Checking for signal duplicates..."
	@python scripts/data/check_signal_duplicates.py

clean-duplicates:
	@echo "🧹 Cleaning duplicates..."
	@python scripts/data/clean_duplicates.py

create-test-data:
	@echo "🔧 Creating test data..."
	@python scripts/data/create_extra_charge_test_data.py
	@python scripts/data/create_test_installation.py

# Development helpers
demo-installation:
	@echo "🎬 Running installation demo..."
	@python scripts/dev/demo_new_installation_logic.py

verify-photos:
	@echo "📸 Verifying photo uploads..."
	@python scripts/dev/verify_photo_upload.py

analyze-workflow:
	@echo "🔬 Analyzing rejection workflow..."
	@python scripts/dev/analyze_rejection_workflow.py

# Fixes and migrations
fix-billing:
	@echo "🔧 Fixing billing customers..."
	@python scripts/fixes/fix_billing_customers.py

verify-billing:
	@echo "✅ Verifying billing creation..."
	@python scripts/fixes/verify_billing_creation.py

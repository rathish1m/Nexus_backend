# Nexus Backend

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Django Version](https://img.shields.io/badge/django-5.2.1-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Build Status](https://github.com/otace1/nexus_backend/actions/workflows/tests.yml/badge.svg)](https://github.com/otace1/nexus_backend/actions/workflows/tests.yml)

A robust and scalable Django backend for the Nexus Telecoms platform, providing telecommunications services with order management, payments, KYC, and multi-tenant support.

## 🚀 Features

### Core Features
- ✅ **User Management** - Complete authentication and authorization
- ✅ **Order Management** - Starlink order creation and tracking
- ✅ **Integrated Payments** - Support for Stripe, FlexPay, and other methods
- ✅ **KYC Management** - Identity verification for individuals and businesses
- ✅ **Inventory Management** - Equipment inventory and movements
- ✅ **BI Dashboards** - Business analytics and reports
- ✅ **REST API** - Complete programmatic interface
- ✅ **Admin Interface** - Django admin panel
- ✅ **Client Feedback** - Post-installation feedback workflow with audit trail

### Advanced Technologies
- 🔄 **Asynchronous Tasks** - Celery for background operations
- 🐳 **Containerization** - Full Docker support
- 📊 **Database** - MySQL/PostgreSQL with migrations
- 🔒 **Security** - JWT authentication, encryption, audit logs
- 📧 **Notifications** - Integrated email and SMS
- 🌍 **Internationalization** - Multi-language support (FR/EN)
- 📱 **Mobile API** - Optimized for mobile applications

## � Documentation

Complete documentation is available in the [`docs/`](./docs/) directory:

- **[Documentation Index](./docs/INDEX.md)** - Master navigation for all documentation
- **[RBAC Security System](./docs/security/RBAC_INDEX.md)** - Role-based access control
- **[Project Summary](./docs/PROJECT_FINAL_SUMMARY.md)** - Complete project overview

### Quick Links by Topic

| Topic | Documentation |
|-------|--------------|
| 🔒 **Security & RBAC** | [docs/security/](./docs/security/) |
| 💰 **Billing System** | [docs/billing/](./docs/billing/) |
| 🌍 **Translations** | [docs/translations/](./docs/translations/) |
| 🏗️ **Installations** | [docs/installations/](./docs/installations/) |
| 📋 **Surveys** | [docs/surveys/](./docs/surveys/) |
| 💳 **Payments** | [docs/payments/](./docs/payments/) |
| ✨ **Features** | [docs/features/](./docs/features/) |
| 📘 **Guides** | [docs/guides/](./docs/guides/) |

## �🛠️ Technology Stack

### Backend
- **Django 5.2.1** - Main web framework
- **Django REST Framework** - REST API
- **Celery** - Asynchronous tasks
- **Redis/Valkey** - Cache and message broker

### Database
- **MySQL 8.0+** / **PostgreSQL 13+**
- **Django ORM** - Migrations and queries

### Payments & Communications
- **Stripe** - International payments
- **FlexPay** - Local payments
- **Twilio** - SMS and communications
- **SendGrid** - Transactional emails

### DevOps & Deployment
- **Docker** - Containerization
- **Gunicorn** - WSGI server
- **Nginx** - Reverse proxy (production)
- **Sentry** - Monitoring and error tracking

### Development
- **Python 3.11+**
- **pytest** - Unit and integration tests
- **Black** - Code formatting
- **Flake8** - Linting
- **Coverage** - Coverage analysis

## 🗺️ Running GIS/PostGIS Tests Locally

Some billing and revenue reporting tests (e.g. `revenue_table`, region resolution) require a spatial database backend (PostGIS). CI already runs them against PostGIS; you can mirror this locally with Docker.

### 1. Start a local PostGIS test database

From the project root:

```bash
docker compose -f docker-compose.test.yml up -d
```

This starts a PostGIS container using `docker-compose.test.env`:

- Host: `localhost`
- Port: `5433`
- Database: `nexus_test`
- User: `nexus_test`
- Password: `secret`

### 2. Configure `.env.test` for PostGIS tests

The test runner (`make test`, `make test-cov`, `make test-cov-open`) loads `.env.test` via `scripts/run_tests.sh`.

To ensure all GIS-dependent tests run:

- Use the PostGIS URL in `.env.test`:

  ```env
  # Database Configuration (use local PostGIS test DB for GIS-dependent tests)
  DATABASE_URL=postgis://nexus_test:secret@127.0.0.1:5433/nexus_test
  ```

- Keep `TESTING=True` in `.env.test` so `nexus_backend.settings` uses the test DB block.
- To opt into a few extra GeoDjango-heavy tests (e.g. password reset flow), add:

  ```env
  USE_POSTGIS_TESTS=1
  ```

> Tip: If you see skips like “Spatial database backend is not available for tests.” when running `pytest -rs`, it usually means `DATABASE_URL` was not pointing to PostGIS when the tests started.

### 3. (Alternative) Point Django tests to PostGIS via env vars

If you prefer not to edit `.env.test`, you can override settings directly in your shell:

Enable test mode and set `DATABASE_URL` so `nexus_backend.settings` picks the PostGIS backend:

```bash
export TESTING=1
export DATABASE_URL=postgres://nexus_test:secret@localhost:5433/nexus_test
```

### 4. Run migrations against the test DB

With the same environment variables set:

```bash
venv/bin/python manage.py migrate
```

This creates all tables in the `nexus_test` PostGIS database.

### 5. Run the tests (including GIS-backed ones)

Now the GIS-dependent tests will run locally instead of being skipped:

```bash
# All tests
venv/bin/pytest -q

# Or just billing views (revenue_summary, revenue_table, region checks)
venv/bin/pytest billing_management/tests/test_billing_views.py -q
```

If `TESTING=1` and `DATABASE_URL` point to a PostGIS database, `django.db.connection.ops` exposes spatial capabilities and the GIS tests will behave the same locally as in CI.

## 📋 Prerequisites

- Python 3.11 or higher
- Docker & Docker Compose (recommended)
- MySQL 8.0+ or PostgreSQL 13+
- Redis/Valkey 6.0+
- Git

## 🚀 Installation & Setup

### 1. Repository Cloning

```bash
git clone https://github.com/your-org/nexus_backend.git
cd nexus_backend
```

### 2. Environment Setup

#### With Docker (Recommended)

```bash
# Copy environment template
cp .env.example .env

# Build and run services
make docker-build
make docker-run

# Or use docker-compose
docker-compose up -d
```

#### Local Installation

```bash
# Create virtual environment
make venv
source venv/bin/activate  # Linux/Mac
# or venv\Scripts\activate  # Windows

# Install dependencies
make install-dev

# Database setup
cp .env.example .env
# Edit .env with your settings
```

### 3. Database Setup

```bash
# Create database
make create-db

# Run migrations
make migrate
```

### 4. Static Files Collection

```bash
make collectstatic
```

## 🏃‍♂️ Usage

### Development Server Startup

```bash
# With Makefile
make runserver

# Or directly
python manage.py runserver
```

The server will be accessible at `http://localhost:8000`

### Available Commands

Use `make help` to see all available commands:

```bash
make help
```

### Feedback API

The client feedback module exposes REST endpoints under `/api/feedbacks/`:

- `POST /api/feedbacks/` — create or update feedback for a job (idempotent on `job_id`).
- `GET /api/feedbacks/my?job=<id>` — fetch the authenticated customer's feedback.
- `POST /api/feedbacks/<id>/attachments/` — upload an attachment (customers within edit window, staff anytime).
- `DELETE /api/feedbacks/attachments/<id>/` — remove an attachment.
- `POST /api/feedbacks/<id>/lock|pin|reply/` — internal staff moderation actions.

Permissions are enforced via existing session/JWT authentication combined with customer ownership and staff roles (`support`, `qa`, `admin`).

#### Essential Commands

```bash
# Testing
make test              # Full tests
make test-cov          # Tests with coverage
make test-fast         # Fast tests

# Code Quality
make lint              # Code linting
make format            # Auto formatting

# Database
make migrate           # Run migrations
make backup-db         # Database backup
make reset-db          # Database reset (WARNING)

# Services
make celery-worker     # Start Celery worker
make celery-beat       # Start Celery scheduler
make flower            # Flower monitoring interface

# Internationalization (i18n)
make i18n-extract      # Extract translatable strings
make i18n-compile      # Compile translation files
make i18n-update       # Update and compile translations
make i18n-check        # Check translation coverage
```

## 🌍 Rosetta - Translation Management

**Django Rosetta** is integrated for intuitive web-based translation management.

### Access Rosetta Interface

1. **Start the development server:**
   ```bash
   make runserver
   ```

2. **Access Rosetta at:**
   ```
   http://localhost:8000/admin/rosetta/
   ```

3. **Login with Django admin credentials**

### Rosetta Features

- 🌐 **Web Interface** - No command line required for translations
- 📝 **Real-time Editing** - Visual editing of translation strings
- 🔍 **Search & Filter** - Find specific strings quickly
- 📊 **Progress Tracking** - See translation completion status
- 🛡️ **Permissions** - Role-based access control
- 🔄 **Version Control** - Git integration ready

### Translation Workflow

#### 1. Extract Strings
```bash
make i18n-extract
# This automatically excludes venv files
```

#### 2. Translate in Rosetta
- Go to `http://localhost:8000/admin/rosetta/`
- Select language (e.g., French)
- Translate the new strings
- Save changes

#### 3. Compile & Test
```bash
make i18n-compile
make runserver
# Test translations in the browser
```

### Supported Languages

- 🇺🇸 **English (en)** - Source language, reference
- 🇫🇷 **French (fr)** - Primary interface language
- ➕ **Extensible** - Easy to add new languages

### Professional Features

- **Context Preservation** - See string usage context
- **Plural Forms** - Advanced pluralization support
- **String Validation** - Format string validation
- **Team Collaboration** - Multiple translators support
- **Quality Assurance** - Translation consistency checks

### Configuration

Rosetta is pre-configured in your Django settings:

```python
# settings.py
INSTALLED_APPS = [
    # ... other apps
    'rosetta',
]

# URL patterns in urls.py
path('admin/rosetta/', include('rosetta.urls')),
```

## 🧪 Testing

### Running Tests

```bash
# Full tests with coverage
make test-cov

# Fast tests (without coverage)
make test-fast

# Specific tests
pytest apps/users/tests/test_models.py
pytest apps/orders/tests/ -v
```

### View Coverage in Browser

- Generate coverage and open the HTML report automatically:

```bash
make test-cov-open
```

- Or generate first, then open manually:

```bash
make test-cov
# Then open the report
make coverage-open         # tries xdg-open/open
# or directly open htmlcov/index.html in your browser
```

The summary also prints in the terminal (TOTAL line) thanks to `--cov-report=term`.

### Running tests with PostGIS (local Docker)

If your project uses GeoDjango/PostGIS (this repo does), you can run a local Postgres+PostGIS instance for tests using the provided docker-compose file.

1. Start the test DB:

```bash
docker compose -f docker-compose.test.yml up -d
```

2. (Optional) Create the PostGIS extension inside the database (should already be present in the image, but run if needed):

```bash
docker exec -it $(docker compose -f docker-compose.test.yml ps -q postgis) \
  psql -U nexus_test -d nexus_test -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

3. Point pytest to the test DB. If your Django settings read env vars like `DATABASE_URL`, set it appropriately. Example:

```bash
export DATABASE_URL=postgres://nexus_test:secret@127.0.0.1:5433/nexus_test
PYTHONPATH=. DATABASE_URL=$DATABASE_URL pytest -q
```

4. When finished, stop the test DB:

```bash
docker compose -f docker-compose.test.yml down
```

I also added simple `Makefile` targets to simplify these steps (see `Makefile` in repo root).


### Code Quality

```bash
# Linting
make lint

# Auto formatting
make format

# Security checks
make check-security
```

## 📁 Project Structure

```
nexus_backend/
├── api/                    # REST API endpoints
├── main/                   # Core application
├── client_app/            # Client-facing views
├── orders/                # Order management
├── payments/              # Payment processing
├── kyc_management/        # KYC verification
├── stock/                 # Inventory management
├── dashboard_bi/          # Business intelligence
├── user/                  # User management
├── subscriptions/         # Subscription handling
├── nexus_backend/         # Django project settings
├── static/                # Static files
├── templates/             # HTML templates
├── tests/                 # Test suite
├── docker/                # Docker configuration
├── docs/                  # Documentation
├── .env.example          # Environment template
├── docker-compose.yml    # Docker services
├── Dockerfile           # Container definition
├── Makefile             # Development commands
├── pytest.ini           # Test configuration
├── requirements.txt     # Production dependencies
└── requirements-dev.txt # Development dependencies
```

## 🔧 Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
# Django
DJANGO_SECRET_KEY=your-secret-key
DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASES_URL=mysql://user:password@localhost:3306/nexus_db

# Redis/Valkey
VALKEY_URL=redis://localhost:6379/0

# External Services
STRIPE_SECRET_KEY=sk_test_...
FLEXPAY_MERCHANT_ID=...
TWILIO_ACCOUNT_SID=...
SENDGRID_API_KEY=...

# Email
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587

# Monitoring
SENTRY_DSN=https://...
```

### Docker Configuration

The project includes complete Docker configuration:

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
    depends_on:
      - db
      - redis

  db:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: nexus_db

  redis:
    image: redis:7-alpine
```

## 🚀 Deployment

### Production

1. **Build Docker Image**
   ```bash
   make docker-build
   ```

2. **Production Configuration**
   ```bash
   # Environment variables
   DEBUG=False
   SECRET_KEY=production-secret
   ALLOWED_HOSTS=yourdomain.com
   ```

3. **External Services**
   - MySQL/PostgreSQL database
   - Redis/Valkey for cache and Celery
   - Static file service (S3/CloudFlare)
   - Monitoring (Sentry)

### Staging

```bash
# Use docker-compose for staging
docker-compose -f docker-compose.staging.yml up -d
```

## 📊 Monitoring & Observability

### Available Metrics

- **Performance** - Response times, throughput
- **Errors** - Error logs with Sentry
- **Database** - Slow queries, connections
- **Cache** - Redis hit/miss rates
- **Tasks** - Celery task status

### Monitoring Commands

```bash
# Flower interface for Celery
make flower

# Application logs
docker logs nexus-backend

# System metrics
docker stats
```

## 🔒 Security

### Implemented Measures

- ✅ **Encryption** - Sensitive data encryption
- ✅ **Authentication** - JWT tokens, secure sessions
- ✅ **Authorization** - Granular permissions
- ✅ **Audit** - Logs for all sensitive actions
- ✅ **Validation** - Input sanitization
- ✅ **Rate Limiting** - DoS attack protection
- ✅ **HTTPS** - In-transit encryption
- ✅ **CSP** - Content Security Policy

### Security Checks

```bash
# Static analysis
make check-security

# Vulnerable dependencies
safety check

# Security scan
bandit -r .
```

## 🤝 Contributing

### Contribution Process

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Code Standards

- **PEP 8** for Python style
- **Black** for automatic formatting
- **Tests** required for all new features
- **Documentation** kept up to date

### Pre-commit Hooks

```bash
# Install hooks
pip install pre-commit
pre-commit install

# Manual execution
pre-commit run --all-files
```

## 📚 Documentation

### Developer Documentation

- [Architecture](./docs/architecture.md)
- [API Documentation](./docs/api.md)
- [Deployment](./docs/deployment.md)
- [Security](./docs/security.md)

### User Guides

- [Installation](./docs/installation.md)
- [Configuration](./docs/configuration.md)
- [Troubleshooting](./docs/troubleshooting.md)

## 🐛 Troubleshooting

### Common Issues

#### Database Connection Error
```bash
# Check environment variables
cat .env | grep DATABASE

# Test connection
python manage.py dbshell
```

#### Celery Issues
```bash
# Check worker status
make celery-worker

# Celery logs
celery -A nexus_backend worker --loglevel=debug
```

#### Migration Errors
```bash
# List migrations
python manage.py showmigrations

# Rollback if necessary
python manage.py migrate app_name 0001
```

## Sonarqube Scanning
```
pysonar --sonar-host-url=http://localhost:9000 \
  --sonar-token=sqp_83f861e1d7981f06b0ca25ad62443465a8c3d552 \
  --sonar-project-key=nexus_backend
```
Note that those values may change.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👥 Team & Support

- **Technical Team** : [tech@nexus-telecoms.com](mailto:tech@nexus-telecoms.com)
- **Customer Support** : [support@nexus-telecoms.com](mailto:support@nexus-telecoms.com)
- **Documentation** : [docs.nexus-telecoms.com](https://docs.nexus-telecoms.com)

## 🙏 Acknowledgments

- Django Community
- Open Source Contributors
- Our exceptional development team

---

**Nexus Telecoms** - Connecting Africa to the future 🚀

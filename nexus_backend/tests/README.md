# Testing Guide

This document explains how to use the testing architecture set up for this Django project.

## Overview

The testing setup uses:
- **pytest** as the test runner
- **pytest-django** for Django integration
- **factory-boy** for creating test data
- **coverage** for measuring test coverage
- **faker** for generating realistic test data

## Project Structure

```
tests/
├── __init__.py
├── README.md
├── test_models.py      # Model tests
└── test_views.py       # View tests

main/
└── factories.py        # Test data factories

conftest.py             # Shared fixtures
pytest.ini             # Pytest configuration
.coveragerc           # Coverage configuration
Makefile              # Test commands
```

## Running Tests

### Basic Commands

```bash
# Run all tests
make test

# Run tests with coverage
make test-cov

# Run tests fast (stop on first failure)
make test-fast

# Run specific test file
pytest tests/test_models.py

# Run specific test class
pytest tests/test_models.py::TestUserModel

# Run specific test method
pytest tests/test_models.py::TestUserModel::test_user_creation
```

### Test Categories

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only slow tests
pytest -m slow

# Run tests requiring database
pytest -m django_db
```

## Writing Tests

### Test Structure

```python
import pytest
from django.test import Client
from main.factories import UserFactory

@pytest.mark.django_db
class TestExample:
    """Test class for Example model/view."""

    def test_example_creation(self):
        """Test basic creation."""
        obj = UserFactory()
        assert obj.username
        assert obj.is_active

    def test_example_method(self, authenticated_client):
        """Test with fixtures."""
        response = authenticated_client.get('/some-url/')
        assert response.status_code == 200
```

### Available Fixtures

- `client`: Django test client
- `user`: Regular test user
- `staff_user`: Staff test user
- `authenticated_client`: Client logged in as regular user
- `staff_client`: Client logged in as staff user

### Using Factories

```python
from main.factories import UserFactory, OrderFactory

# Create basic objects
user = UserFactory()
order = OrderFactory()

# Create with custom attributes
user = UserFactory(full_name="John Doe", email="john@example.com")
order = OrderFactory(kit_price_usd=100, plan_price_usd=50)
```

## Best Practices

### 1. Test Organization
- Group related tests in classes
- Use descriptive test method names
- Keep tests focused and small

### 2. Database Tests
- Use `@pytest.mark.django_db` for tests needing database
- Use factories instead of manual object creation
- Clean up test data automatically

### 3. Fixtures
- Use fixtures for reusable test data
- Keep fixtures in `conftest.py` for sharing
- Use factory-boy for complex object creation

### 4. Assertions
- Use specific assertions
- Test both positive and negative cases
- Check edge cases and error conditions

### 5. Coverage
- Aim for >80% code coverage
- Focus on critical business logic
- Exclude generated code and simple getters

## Continuous Integration

For CI/CD pipelines, use:

```yaml
# GitHub Actions example
- name: Run Tests
  run: |
    pip install -r requirements.txt
    pytest --cov=. --cov-report=xml

- name: Upload Coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure `DJANGO_SETTINGS_MODULE` is set correctly
2. **Database errors**: Use `@pytest.mark.django_db` for database tests
3. **Fixture errors**: Check fixture definitions in `conftest.py`
4. **Coverage issues**: Update `.coveragerc` to exclude unnecessary files

### Debug Mode

```bash
# Run tests with verbose output
pytest -v

# Run tests with debug information
pytest -s --pdb

# Show coverage details
pytest --cov=. --cov-report=term-missing
```

## Performance Tips

- Use `pytest-xdist` for parallel test execution
- Use `--tb=short` for faster failure output
- Cache test results with `pytest-cache`
- Use `pytest-randomly` to catch order-dependent tests

#!/bin/bash
# Script to check and add missing environment variables

ENV_FILE=".env"
ENV_EXAMPLE=".env.example"

echo "🔍 Checking for missing environment variables..."

# Check if .env exists
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found. Creating from .env.example..."
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "✅ Created .env file. Please update it with your actual values."
    exit 0
fi

# List of critical variables that must exist
CRITICAL_VARS=(
    "CELERY_BROKER_URL"
    "CELERY_RESULT_BACKEND"
    "REDIS_URL"
    "DATABASE_URL"
    "DJANGO_SECRET_KEY"
)

MISSING_VARS=()

# Check each critical variable
for var in "${CRITICAL_VARS[@]}"; do
    if ! grep -q "^$var=" "$ENV_FILE"; then
        MISSING_VARS+=("$var")
    fi
done

# If variables are missing, add them
if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "⚠️  Found ${#MISSING_VARS[@]} missing variable(s):"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done

    echo ""
    echo "📝 Adding missing variables with default local development values..."

    # Add missing variables to .env
    for var in "${MISSING_VARS[@]}"; do
        case $var in
            CELERY_BROKER_URL)
                echo "" >> "$ENV_FILE"
                echo "# Celery Configuration (added by check_env.sh)" >> "$ENV_FILE"
                echo "CELERY_BROKER_URL=redis://localhost:6379/0" >> "$ENV_FILE"
                echo "✅ Added CELERY_BROKER_URL"
                ;;
            CELERY_RESULT_BACKEND)
                echo "CELERY_RESULT_BACKEND=redis://localhost:6379/0" >> "$ENV_FILE"
                echo "✅ Added CELERY_RESULT_BACKEND"
                ;;
            REDIS_URL)
                echo "" >> "$ENV_FILE"
                echo "# Redis Configuration (added by check_env.sh)" >> "$ENV_FILE"
                echo "REDIS_URL=redis://localhost:6379/0" >> "$ENV_FILE"
                echo "✅ Added REDIS_URL"
                ;;
            DATABASE_URL)
                echo "" >> "$ENV_FILE"
                echo "# Database Configuration (added by check_env.sh)" >> "$ENV_FILE"
                echo "DATABASE_URL=postgresql://user:password@localhost:5432/nexus_db" >> "$ENV_FILE"
                echo "⚠️  Added DATABASE_URL - PLEASE UPDATE WITH YOUR ACTUAL DATABASE CREDENTIALS"
                ;;
            DJANGO_SECRET_KEY)
                # Generate a random secret key
                SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
                echo "" >> "$ENV_FILE"
                echo "# Django Configuration (added by check_env.sh)" >> "$ENV_FILE"
                echo "DJANGO_SECRET_KEY=$SECRET_KEY" >> "$ENV_FILE"
                echo "✅ Added DJANGO_SECRET_KEY (randomly generated)"
                ;;
        esac
    done

    echo ""
    echo "✅ Environment variables updated successfully!"
    echo "⚠️  Please review .env file and update values as needed for your environment."
else
    echo "✅ All critical environment variables are present!"
fi

echo ""
echo "📋 Current .env variables:"
grep "^[A-Z]" "$ENV_FILE" | cut -d'=' -f1 | sort

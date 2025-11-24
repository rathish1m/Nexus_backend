# Security Best Practices for Django Secret Management

## ⚠️ CRITICAL: Never Commit Secrets to Git

### What NOT to do:
- ❌ Never hardcode `SECRET_KEY` or any sensitive data in Python files
- ❌ Never commit `.env` files with real credentials
- ❌ Never leave secrets in comments (even commented out!)
- ❌ Never push API keys, passwords, or tokens to version control

### What TO do:
- ✅ Always use environment variables for secrets
- ✅ Keep `.env` in `.gitignore`
- ✅ Use `.env.example` to document required variables (without real values)
- ✅ Rotate secrets immediately if accidentally committed

## 🔐 Django SECRET_KEY Management

### Generating a New SECRET_KEY

```bash
# Method 1: Using Django's built-in utility
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Method 2: Using Python secrets module
python -c 'import secrets; print(secrets.token_urlsafe(50))'
```

### Setting Up Environment Variables

1. **Development (Local)**:
   ```bash
   # Copy the example file
   cp .env.example .env

   # Edit .env and set your SECRET_KEY
   # DJANGO_SECRET_KEY=your-newly-generated-secret-key-here
   ```

2. **Production (Server)**:
   - Use your hosting provider's environment variable management
   - Examples:
     - Heroku: `heroku config:set DJANGO_SECRET_KEY="your-key"`
     - AWS: Use AWS Secrets Manager or Parameter Store
     - DigitalOcean: Use App Platform environment variables
     - Docker: Use Docker secrets or environment files

## 🔄 What to Do if a Secret is Leaked

If you accidentally commit a secret to Git:

### 1. **Immediately Revoke the Compromised Secret**
```bash
# Generate a new SECRET_KEY
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Update your .env file with the new key
# Update production environment variables
```

### 2. **Rotate All Related Credentials**
- Database passwords
- API keys (Stripe, Twilio, SendGrid, etc.)
- OAuth tokens
- Third-party service credentials

### 3. **Remove from Git History** (if needed)
```bash
# WARNING: This rewrites history and affects all collaborators
# Use git-filter-repo (recommended) or BFG Repo-Cleaner
pip install git-filter-repo

# Remove the file from history
git filter-repo --path .env --invert-paths

# Force push (WARNING: affects all collaborators)
git push --force --all
```

### 4. **Alternative: Start Fresh**
If the repository is not widely distributed:
```bash
# Create a new repository
# Copy only the code (not .git directory)
# Initialize fresh Git history
# Push to new remote
```

## 📋 Environment Variables Checklist

Before deploying to production, verify:

- [ ] `DJANGO_SECRET_KEY` is set and unique
- [ ] `DEBUG=False` in production
- [ ] `ALLOWED_HOSTS` is properly configured
- [ ] Database credentials are secure
- [ ] All API keys are environment variables
- [ ] `.env` file is in `.gitignore`
- [ ] `.env.example` is up to date (without real values)
- [ ] SSL/TLS settings are enabled
- [ ] CORS settings are properly configured

## 🛡️ Additional Security Measures

### 1. Use a Secrets Manager
For production, consider using:
- AWS Secrets Manager
- HashiCorp Vault
- Azure Key Vault
- Google Cloud Secret Manager

### 2. Enable Security Headers
Already configured in `settings.py`:
```python
SECURE_SSL_REDIRECT = True  # Force HTTPS
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
```

### 3. Regular Security Audits
```bash
# Check for security issues
python manage.py check --deploy

# Scan dependencies for vulnerabilities
pip install safety
safety check

# Run Django security checks
python manage.py check --tag security
```

## 📚 Resources

- [Django Security Best Practices](https://docs.djangoproject.com/en/stable/topics/security/)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)

## ⚡ Quick Reference

### Check if .env is ignored:
```bash
git check-ignore .env
# Should output: .env
```

### Verify no secrets in code:
```bash
# Search for potential secrets
grep -r "SECRET_KEY" --include="*.py" .
grep -r "API_KEY" --include="*.py" .
grep -r "password" --include="*.py" .
```

### Test environment variables:
```python
# In Django shell
python manage.py shell
>>> from django.conf import settings
>>> print(len(settings.SECRET_KEY))  # Should be 50+
>>> print(settings.DEBUG)  # Should be False in production
```

---

**Remember**: Security is not a one-time task. Regularly review and update your security practices.

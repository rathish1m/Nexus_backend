# Password Hashing Security Guide

## 🔐 Overview

This project uses **Argon2** for password hashing, which is the most secure algorithm available and the winner of the 2015 Password Hashing Competition.

## 📊 Configured Password Hashers

The application is configured with multiple password hashers in order of preference:

1. **Argon2** (Primary) - Most secure, memory-hard algorithm
2. **PBKDF2** (Fallback) - Django default, widely supported
3. **PBKDF2-SHA1** (Legacy) - For backward compatibility
4. **BCrypt-SHA256** (Alternative) - Another strong option

### Why Argon2?

- ✅ **Winner of Password Hashing Competition 2015**
- ✅ **Memory-hard algorithm** - Resistant to GPU/ASIC attacks
- ✅ **Configurable parameters** - Memory, iterations, and parallelism
- ✅ **Side-channel resistant**
- ✅ **Industry best practice** as recommended by OWASP

### Algorithm Comparison

| Algorithm | Security Level | Speed | Memory Usage | Recommended |
|-----------|---------------|-------|--------------|-------------|
| **Argon2** | ⭐⭐⭐⭐⭐ Excellent | Medium | High | ✅ Yes |
| **PBKDF2** | ⭐⭐⭐⭐ Good | Fast | Low | ✅ Yes (fallback) |
| **BCrypt** | ⭐⭐⭐⭐ Good | Medium | Medium | ✅ Yes (alternative) |
| **MD5** | ⭐ Poor | Very Fast | Very Low | ❌ **NEVER USE** |
| **SHA1** | ⭐⭐ Weak | Fast | Low | ❌ Not recommended |

## 🛠️ Implementation

### Production Configuration

```python
# nexus_backend/settings.py
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",  # Primary
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",  # Fallback
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",  # Legacy
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",  # Alternative
]
```

### Test Configuration

For testing, we use PBKDF2 instead of Argon2 to improve test performance while maintaining security:

```python
# Test settings (activated when running pytest)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
```

**Why?** Tests don't need the extra security of Argon2 since they use temporary databases. PBKDF2 provides a good balance between security and test speed.

## 📦 Dependencies

Required packages (already in `requirements.txt`):

```txt
argon2-cffi==23.1.0  # For Argon2 support
bcrypt==4.2.1        # For BCrypt support (optional)
```

To install:
```bash
pip install argon2-cffi bcrypt
```

## 🔄 Password Upgrade Strategy

Django automatically upgrades passwords to the preferred hasher when users log in:

1. User logs in with old password (e.g., hashed with PBKDF2)
2. Django verifies the password using the old hasher
3. Django re-hashes the password using Argon2 (first in the list)
4. Next login will use Argon2

This means all passwords will gradually migrate to Argon2 without user intervention.

## ⚠️ Security Warnings

### Never Use These Hashers

```python
# ❌ INSECURE - DO NOT USE
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",  # VULNERABLE
    "django.contrib.auth.hashers.UnsaltedMD5PasswordHasher",  # EXTREMELY VULNERABLE
    "django.contrib.auth.hashers.SHA1PasswordHasher",  # WEAK
    "django.contrib.auth.hashers.UnsaltedSHA1PasswordHasher",  # EXTREMELY VULNERABLE
    "django.contrib.auth.hashers.CryptPasswordHasher",  # OUTDATED
]
```

### SonarQube Warnings

If SonarQube reports password hashing issues:

- **"Use a secure hashing algorithm"** → Ensure Argon2 or PBKDF2 is first in `PASSWORD_HASHERS`
- **"MD5PasswordHasher detected"** → Remove MD5 from production settings (only use in tests if needed)
- **"Hardcoded credentials"** → Check for test passwords in code

## 🧪 Testing Password Hashing

```python
from django.contrib.auth.hashers import make_password, check_password

# Hash a password
hashed = make_password("SecurePassword123!")
print(hashed)  # argon2$argon2id$v=19$m=102400,t=2,p=8$...

# Verify a password
is_valid = check_password("SecurePassword123!", hashed)
print(is_valid)  # True
```

## 📚 References

- [Django Password Management Documentation](https://docs.djangoproject.com/en/5.2/topics/auth/passwords/)
- [Argon2 Official Specification](https://github.com/P-H-C/phc-winner-argon2)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Password Hashing Competition](https://www.password-hashing.net/)

## ✅ Checklist

- [x] Argon2 installed (`argon2-cffi` package)
- [x] Argon2 configured as primary hasher
- [x] PBKDF2 configured as fallback
- [x] MD5/SHA1 removed from production settings
- [x] Test configuration uses secure hasher (PBKDF2)
- [x] All dependencies documented in `requirements.txt`
- [x] Password upgrade strategy understood

## 🔍 Monitoring

To check which algorithm is being used for existing passwords:

```python
from main.models import User

for user in User.objects.all():
    password_field = user.password
    algorithm = password_field.split('$')[0] if '$' in password_field else 'unknown'
    print(f"{user.email}: {algorithm}")
```

Expected output:
- New passwords: `argon2`
- Migrating passwords: `pbkdf2_sha256` (will upgrade on next login)
- Legacy passwords: Other algorithms (will upgrade on next login)

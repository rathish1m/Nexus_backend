"""
Run the password reset flow manually (non-pytest helper).
Duplicate of scripts/test_password_reset_flow.py but named so pytest won't collect it.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.test import Client
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()
email = "test_reset@example.com"
username = "test_reset_user"
password_before = "OldPassword123!"
password_after = "NewPassword456!"

user, created = User.objects.get_or_create(email=email, defaults={"username": username})
if created:
    user.set_password(password_before)
    user.save()
    print("Created test user:", email)
else:
    print("Found existing test user:", email)

uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
token = default_token_generator.make_token(user)

reset_path = f"/en/user/password_reset_confirm/{uidb64}/{token}/"
print("\nReset URL (GET):", reset_path)

client = Client()

# GET
resp = client.get(reset_path)
print("\nGET status code:", resp.status_code)
open("/tmp/test_reset_get.html", "wb").write(resp.content)
print("Saved GET response to /tmp/test_reset_get.html")

# POST new password
resp_post = client.post(
    reset_path, {"password": password_after, "password2": password_after}
)
print("\nPOST status code:", resp_post.status_code)
open("/tmp/test_reset_post.html", "wb").write(resp_post.content)
print("Saved POST response to /tmp/test_reset_post.html")

# Verify login with new password
login_ok = client.login(email=email, password=password_after) or client.login(
    username=username, password=password_after
)
print("\nLogin with new password OK:", login_ok)
# Clean up: remove the test user to avoid polluting the DB
try:
    user.delete()
    print("\nDeleted test user:", email)
except Exception as e:
    print("\nFailed to delete test user:", e)

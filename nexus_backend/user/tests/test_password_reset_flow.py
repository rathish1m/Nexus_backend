import os

import pytest

from django.conf import settings
from django.test import Client, TestCase

# If the project is not using PostGIS (GeoDjango), skip these tests locally unless
# the developer explicitly opts in by setting USE_POSTGIS_TESTS=1 in the environment.
engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
if "postgis" not in engine and not os.getenv("USE_POSTGIS_TESTS"):
    pytest.skip(
        "Skipping GeoDjango-dependent test: PostGIS not available in DATABASES['default'].ENGINE (set USE_POSTGIS_TESTS=1 to run)",
        allow_module_level=True,
    )
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class PasswordResetFlowTest(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.email = "test_reset@example.com"
        self.username = "test_reset_user"
        self.old_password = "OldPassword123!"
        self.new_password = "NewPassword456!"
        # Create or get the user
        self.user, created = self.User.objects.get_or_create(
            email=self.email, defaults={"username": self.username}
        )
        if created:
            self.user.set_password(self.old_password)
            self.user.save()

        self.client = Client()

    def tearDown(self):
        # Remove the test user to keep DB clean
        try:
            self.User.objects.filter(email=self.email).delete()
        except Exception:
            pass

    def test_password_reset_confirm_get_and_post(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse(
            "password_reset_confirm", kwargs={"uidb64": uidb64, "token": token}
        )

        # GET the reset page and ensure the form is present
        resp_get = self.client.get(url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'name="password"')
        self.assertContains(resp_get, 'name="password2"')

        # POST new password
        resp_post = self.client.post(
            url, {"password": self.new_password, "password2": self.new_password}
        )
        self.assertEqual(resp_post.status_code, 200)
        # Reload user and assert password changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.new_password))
        # Confirm success message present
        self.assertContains(resp_post, "Your password has been reset")

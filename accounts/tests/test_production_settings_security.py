from __future__ import annotations

import os
from datetime import timedelta

from django.conf import settings
from django.test import SimpleTestCase


class ProductionSettingsSecurityTests(SimpleTestCase):
    """
    Production hardening checks.

    These tests intentionally fail against local/dev settings that contain hardcoded
    credentials, DEBUG=True, empty ALLOWED_HOSTS, or missing HTTPS cookie/HSTS flags.
    In the strict package these run by default and should fail against unsafe dev-style settings.
    """

    def test_debug_is_disabled_and_allowed_hosts_are_configured(self):
        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.ALLOWED_HOSTS)
        self.assertNotIn("*", settings.ALLOWED_HOSTS)

    def test_secret_key_is_not_django_insecure_default(self):
        secret_key = getattr(settings, "SECRET_KEY", "")
        self.assertGreaterEqual(len(secret_key), 50)
        self.assertFalse(secret_key.startswith("django-insecure-"))

    def test_sms_and_email_secrets_come_from_environment(self):
        # This avoids accepting committed literals in production settings.
        self.assertEqual(getattr(settings, "SMS_API_KEY", None), os.getenv("SMS_API_KEY"))
        self.assertEqual(getattr(settings, "EMAIL_HOST_PASSWORD", None), os.getenv("EMAIL_HOST_PASSWORD"))
        self.assertEqual(getattr(settings, "EMAIL_HOST_USER", None), os.getenv("EMAIL_HOST_USER"))

    def test_https_cookie_and_hsts_flags_are_enabled(self):
        self.assertTrue(getattr(settings, "SECURE_SSL_REDIRECT", False))
        self.assertTrue(getattr(settings, "SESSION_COOKIE_SECURE", False))
        self.assertTrue(getattr(settings, "CSRF_COOKIE_SECURE", False))
        self.assertGreaterEqual(getattr(settings, "SECURE_HSTS_SECONDS", 0), 31536000)
        self.assertTrue(getattr(settings, "SECURE_HSTS_INCLUDE_SUBDOMAINS", False))
        self.assertTrue(getattr(settings, "SECURE_HSTS_PRELOAD", False))
        self.assertEqual(getattr(settings, "X_FRAME_OPTIONS", "DENY"), "DENY")

    def test_auth_rate_limiting_is_configured_in_drf(self):
        rest_framework = getattr(settings, "REST_FRAMEWORK", {})
        self.assertTrue(rest_framework.get("DEFAULT_THROTTLE_CLASSES"))
        rates = rest_framework.get("DEFAULT_THROTTLE_RATES", {})
        self.assertTrue(rates.get("anon") or rates.get("login"))

    def test_jwt_lifetime_and_rotation_are_production_safe(self):
        jwt_settings = getattr(settings, "SIMPLE_JWT", {})
        self.assertLessEqual(jwt_settings.get("ACCESS_TOKEN_LIFETIME"), timedelta(minutes=30))
        self.assertLessEqual(jwt_settings.get("REFRESH_TOKEN_LIFETIME"), timedelta(days=7))
        self.assertTrue(jwt_settings.get("ROTATE_REFRESH_TOKENS"))
        self.assertTrue(jwt_settings.get("BLACKLIST_AFTER_ROTATION"))

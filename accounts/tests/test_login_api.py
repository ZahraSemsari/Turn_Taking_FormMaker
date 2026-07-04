from __future__ import annotations

import unittest

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from ._auth_test_utils import FAST_PASSWORD_HASHERS, TEST_PASSWORD, create_user


@override_settings(
    PASSWORD_HASHERS=FAST_PASSWORD_HASHERS,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LoginAPITests(APITestCase):
    """Tests for account/login/ via auth-login URL name."""

    def setUp(self):
        self.url = reverse("auth-login")

    def assert_login_success(self, response, *, username, email=None, mobile=None):
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertIn("profile_incomplete", response.data)

        # Never expose secret/authentication material through the user object.
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("otp_code", response.data["user"])
        self.assertNotIn("code_hash", response.data["user"])

        token = AccessToken(response.data["access"])
        self.assertEqual(token["username"], username)
        self.assertEqual(token.get("email"), email)
        self.assertEqual(token.get("mobile"), mobile)

    def test_login_with_username_identifier_returns_jwt_and_sanitized_user(self):
        create_user(username="ali", mobile="09120000001")

        response = self.client.post(
            self.url,
            {"identifier": "ali", "password": TEST_PASSWORD},
            format="json",
        )

        self.assert_login_success(
            response,
            username="ali",
            email=None,
            mobile="09120000001",
        )
        self.assertFalse(response.data["profile_incomplete"])

    def test_login_with_username_is_case_insensitive(self):
        create_user(username="CaseUser", mobile="09120000002")

        response = self.client.post(
            self.url,
            {"identifier": "caseuser", "password": TEST_PASSWORD},
            format="json",
        )

        self.assert_login_success(
            response,
            username="CaseUser",
            email=None,
            mobile="09120000002",
        )

    def test_login_with_mobile_identifier_returns_jwt(self):
        create_user(username="mobileuser", mobile="09120000003")

        response = self.client.post(
            self.url,
            {"identifier": "09120000003", "password": TEST_PASSWORD},
            format="json",
        )

        self.assert_login_success(
            response,
            username="mobileuser",
            email=None,
            mobile="09120000003",
        )

    def test_login_with_verified_email_identifier_returns_jwt_case_insensitive(self):
        create_user(
            username="emailuser",
            email="EmailUser@Example.com",
            mobile="09120000004",
            verified_email=True,
        )

        response = self.client.post(
            self.url,
            {"identifier": "emailuser@example.COM", "password": TEST_PASSWORD},
            format="json",
        )

        self.assert_login_success(
            response,
            username="emailuser",
            email="EmailUser@example.com",  # Django normalizes the domain part.
            mobile="09120000004",
        )

    def test_login_with_unverified_email_is_rejected_without_tokens(self):
        create_user(
            username="unverified",
            email="unverified@example.com",
            mobile="09120000005",
            verified_email=False,
        )

        response = self.client.post(
            self.url,
            {"identifier": "unverified@example.com", "password": TEST_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)        
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertIn("No active account found", str(response.data))
        self.assertNotIn("Email address is not verified", str(response.data))
        self.assertNotIn("verified", str(response.data).lower())

    def test_login_missing_identifier_or_password_is_rejected(self):
        create_user(username="missing", mobile="09120000006")

        bad_payloads = [
            {"password": TEST_PASSWORD},
            {"identifier": "missing"},
            {"identifier": "", "password": TEST_PASSWORD},
            {"identifier": "missing", "password": ""},
        ]

        for payload in bad_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertNotIn("access", response.data)
                self.assertNotIn("refresh", response.data)

    def test_wrong_password_and_unknown_identifier_do_not_return_tokens(self):
        create_user(username="known", mobile="09120000007")

        cases = [
            {"identifier": "known", "password": "WrongPass123!"},
            {"identifier": "unknown", "password": TEST_PASSWORD},
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post(self.url, payload, format="json")
                self.assertIn(
                    response.status_code,
                    {status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED},
                    response.data,
                )
                self.assertNotIn("access", response.data)
                self.assertNotIn("refresh", response.data)
                self.assertNotIn("password", str(response.data).lower())
                self.assertNotIn("hash", str(response.data).lower())

    def test_inactive_user_cannot_login(self):
        create_user(username="inactive", mobile="09120000008", is_active=False)

        response = self.client.post(
            self.url,
            {"identifier": "inactive", "password": TEST_PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)
        self.assertNotIn("access", response.data)

    def test_legacy_username_field_can_be_used_instead_of_identifier(self):
        create_user(username="legacy", mobile="09120000009")

        response = self.client.post(
            self.url,
            {"username": "legacy", "password": TEST_PASSWORD},
            format="json",
        )

        self.assert_login_success(
            response,
            username="legacy",
            email=None,
            mobile="09120000009",
        )

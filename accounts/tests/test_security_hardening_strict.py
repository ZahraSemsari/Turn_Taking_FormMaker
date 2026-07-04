from __future__ import annotations

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ._auth_test_utils import FAST_PASSWORD_HASHERS, TEST_PASSWORD, create_user


@override_settings(PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class AuthSecurityHardeningStrictTests(APITestCase):
    """
    Strict security acceptance tests for login hardening. These tests should fail until the controls are implemented.
    """

    def test_login_endpoint_enforces_bruteforce_throttling_or_lockout(self):
        create_user(username="bruteforce", mobile="09120000500")
        url = reverse("auth-login")

        last_response = None
        for _ in range(10):
            last_response = self.client.post(
                url,
                {"identifier": "bruteforce", "password": "WrongPass123!"},
                format="json",
            )

        self.assertEqual(last_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS, last_response.data)

    def test_login_errors_are_fully_normalized_for_existing_and_non_existing_users(self):
        """
        Current email-verification failure necessarily differs from generic bad-login
        failure. Use this test only if you decide not to reveal verification state at
        login time.
        """
        create_user(
            username="unverifiedstate",
            email="unverifiedstate@example.com",
            mobile="09120000501",
            verified_email=False,
        )
        url = reverse("auth-login")

        unverified = self.client.post(
            url,
            {"identifier": "unverifiedstate@example.com", "password": TEST_PASSWORD},
            format="json",
        )
        unknown = self.client.post(
            url,
            {"identifier": "nobody@example.com", "password": TEST_PASSWORD},
            format="json",
        )

        self.assertEqual(unverified.status_code, unknown.status_code)
        self.assertEqual(unverified.data, unknown.data)

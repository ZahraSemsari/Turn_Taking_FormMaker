from __future__ import annotations

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ._auth_test_utils import FAST_PASSWORD_HASHERS, TEST_PASSWORD, create_user


@override_settings(PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class JwtProtectedAndLogoutTests(APITestCase):
    def setUp(self):
        self.user = create_user(username="jwtuser", mobile="09120000100")
        self.login_url = reverse("auth-login")
        self.refresh_url = reverse("auth-token-refresh")
        self.logout_url = reverse("auth-logout")
        self.protected_url = reverse("auth-protected-debug")

    def login(self):
        response = self.client.post(
            self.login_url,
            {"identifier": "jwtuser", "password": TEST_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data["access"], response.data["refresh"]

    def test_protected_route_requires_bearer_access_token(self):
        anonymous = self.client.get(self.protected_url)
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED, anonymous.data)

        access, _ = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        authenticated = self.client.get(self.protected_url)

        self.assertEqual(authenticated.status_code, status.HTTP_200_OK, authenticated.data)
        self.assertEqual(authenticated.data["detail"], "You are logged in")
        self.assertEqual(authenticated.data["user"]["username"], "jwtuser")
        self.assertNotIn("password", authenticated.data["user"])

    def test_token_refresh_returns_new_access_for_valid_refresh(self):
        _, refresh = self.login()

        response = self.client.post(self.refresh_url, {"refresh": refresh}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("access", response.data)
        self.assertNotIn("password", str(response.data).lower())

    def test_logout_requires_authenticated_user_and_refresh_token(self):
        anonymous = self.client.post(self.logout_url, {"refresh": "anything"}, format="json")
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED, anonymous.data)

        access, _ = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        missing_refresh = self.client.post(self.logout_url, {}, format="json")
        self.assertEqual(missing_refresh.status_code, status.HTTP_400_BAD_REQUEST, missing_refresh.data)
        self.assertIn("refresh", missing_refresh.data)

    def test_logout_blacklists_refresh_token_and_prevents_reuse(self):
        access, refresh = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        logout = self.client.post(self.logout_url, {"refresh": refresh}, format="json")
        self.assertEqual(logout.status_code, status.HTTP_200_OK, logout.data)

        self.client.credentials()
        refresh_after_logout = self.client.post(
            self.refresh_url,
            {"refresh": refresh},
            format="json",
        )
        self.assertIn(
            refresh_after_logout.status_code,
            {status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED},
            refresh_after_logout.data,
        )
        self.assertNotIn("access", refresh_after_logout.data)

    def test_logout_with_invalid_refresh_token_is_rejected(self):
        access, _ = self.login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.post(
            self.logout_url,
            {"refresh": "not-a-real-refresh-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("Invalid or expired refresh token", str(response.data))

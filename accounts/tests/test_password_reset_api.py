from __future__ import annotations

import unittest
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import PhoneOTP

from ._auth_test_utils import FAST_PASSWORD_HASHERS, TEST_PASSWORD, create_user


@override_settings(
    PASSWORD_HASHERS=FAST_PASSWORD_HASHERS,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PasswordResetApiTests(APITestCase):
    def setUp(self):
        self.request_url = reverse("auth-password-reset-request")
        self.confirm_url = reverse("auth-password-reset-otp-confirm")

    @patch("accounts.views.send_sms", return_value=True)
    def test_password_reset_request_by_mobile_is_generic_and_sends_sms_for_existing_user(self, send_sms):
        create_user(username="resetmobile", mobile="09120000400")

        existing = self.client.post(
            self.request_url,
            {"identifier": "09120000400"},
            format="json",
        )
        unknown = self.client.post(
            self.request_url,
            {"identifier": "09120000401"},
            format="json",
        )

        self.assertEqual(existing.status_code, status.HTTP_200_OK, existing.data)
        self.assertEqual(unknown.status_code, status.HTTP_200_OK, unknown.data)
        self.assertEqual(existing.data, unknown.data)
        self.assertEqual(existing.data["method"], "sms")
        send_sms.assert_called_once()
        self.assertEqual(send_sms.call_args.args[0], "09120000400")
        self.assertRegex(send_sms.call_args.args[1], r"^\d{6}$")

    @patch("accounts.views.PasswordResetSerializer.save")
    def test_password_reset_request_by_email_is_generic(self, serializer_save):
        create_user(
            username="resetemail",
            email="reset@example.com",
            mobile="09120000402",
            verified_email=True,
        )

        existing = self.client.post(
            self.request_url,
            {"identifier": "reset@example.com"},
            format="json",
        )
        unknown = self.client.post(
            self.request_url,
            {"identifier": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(existing.status_code, status.HTTP_200_OK, existing.data)
        self.assertEqual(unknown.status_code, status.HTTP_200_OK, unknown.data)
        self.assertEqual(existing.data, unknown.data)
        self.assertEqual(existing.data["method"], "email")
        serializer_save.assert_called_once()

    def test_password_reset_request_requires_identifier(self):
        response = self.client.post(self.request_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("identifier", response.data)

    @patch("accounts.views.send_sms", return_value=True)
    def test_password_reset_request_is_rate_limited_by_otp_cooldown(self, send_sms):
        create_user(username="resetlimit", mobile="09120000403")

        first = self.client.post(self.request_url, {"identifier": "09120000403"}, format="json")
        second = self.client.post(self.request_url, {"identifier": "09120000403"}, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS, second.data)
        self.assertIn("please wait", second.data["detail"].lower())
        send_sms.assert_called_once()

    def test_password_reset_confirm_with_valid_otp_changes_password_and_consumes_otp(self):
        user = create_user(username="confirmreset", mobile="09120000410")
        code = PhoneOTP.request_otp(
            mobile="09120000410",
            purpose=PhoneOTP.Purpose.RESET_PASSWORD,
        )

        response = self.client.post(
            self.confirm_url,
            {
                "mobile": "09120000410",
                "code": code,
                "new_password": "NewStr0ngPass!456",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewStr0ngPass!456"))
        self.assertFalse(user.check_password(TEST_PASSWORD))
        otp = PhoneOTP.objects.get(mobile="09120000410", purpose=PhoneOTP.Purpose.RESET_PASSWORD)
        self.assertTrue(otp.is_used)

    def test_password_reset_confirm_rejects_wrong_code_and_unknown_mobile_generically(self):
        create_user(username="wrongreset", mobile="09120000411")
        PhoneOTP.request_otp(
            mobile="09120000411",
            purpose=PhoneOTP.Purpose.RESET_PASSWORD,
        )

        wrong_code = self.client.post(
            self.confirm_url,
            {
                "mobile": "09120000411",
                "code": "000000",
                "new_password": "NewStr0ngPass!456",
            },
            format="json",
        )
        unknown_mobile = self.client.post(
            self.confirm_url,
            {
                "mobile": "09120000412",
                "code": "000000",
                "new_password": "NewStr0ngPass!456",
            },
            format="json",
        )

        self.assertEqual(wrong_code.status_code, status.HTTP_400_BAD_REQUEST, wrong_code.data)
        self.assertEqual(unknown_mobile.status_code, status.HTTP_400_BAD_REQUEST, unknown_mobile.data)
        self.assertEqual(wrong_code.data, unknown_mobile.data)
        self.assertIn("Invalid or expired verification code", wrong_code.data["detail"])

    def test_password_reset_confirm_requires_all_fields(self):
        payloads = [
            {"code": "123456", "new_password": "NewStr0ngPass!456"},
            {"mobile": "09120000413", "new_password": "NewStr0ngPass!456"},
            {"mobile": "09120000413", "code": "123456"},
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.confirm_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertIn("required", response.data["detail"])

    def test_password_reset_confirm_rejects_common_or_numeric_password(self):
        """
        Security expectation.

        Industrial production should enforce AUTH_PASSWORD_VALIDATORS here as well.
        """
        user = create_user(username="weakreset", mobile="09120000414")
        code = PhoneOTP.request_otp(
            mobile="09120000414",
            purpose=PhoneOTP.Purpose.RESET_PASSWORD,
        )

        response = self.client.post(
            self.confirm_url,
            {
                "mobile": "09120000414",
                "code": code,
                "new_password": "12345678",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        user.refresh_from_db()
        self.assertFalse(user.check_password("12345678"))

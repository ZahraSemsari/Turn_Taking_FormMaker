from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
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
class SignupOtpAndRegistrationTests(APITestCase):
    def setUp(self):
        self.signup_otp_url = reverse("auth-signup-otp-request")
        self.signup_url = reverse("auth-signup")

    @patch("accounts.views.send_sms", return_value=True)
    def test_signup_otp_request_success_creates_hashed_otp_and_sends_sms(self, send_sms):
        response = self.client.post(
            self.signup_otp_url,
            {"mobile": "09120000300"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["detail"], "Verification code sent.")
        send_sms.assert_called_once()
        sent_mobile, sent_code = send_sms.call_args.args
        self.assertEqual(sent_mobile, "09120000300")
        self.assertRegex(sent_code, r"^\d{6}$")

        otp = PhoneOTP.objects.get(mobile="09120000300", purpose=PhoneOTP.Purpose.SIGNUP)
        self.assertNotEqual(otp.code_hash, sent_code)
        self.assertTrue(check_password(sent_code, otp.code_hash))

    @patch("accounts.views.send_sms", return_value=True)
    def test_signup_otp_request_rejects_invalid_mobile_without_sms(self, send_sms):
        invalid_payloads = [
            {},
            {"mobile": ""},
            {"mobile": "9120000301"},
            {"mobile": "08120000301"},
            {"mobile": "0912abc0301"},
            {"mobile": "091200003010"},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.signup_otp_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

        send_sms.assert_not_called()

    @patch("accounts.views.send_sms", return_value=True)
    def test_signup_otp_request_for_existing_mobile_is_rejected_without_sms(self, send_sms):
        create_user(username="existingmobile", mobile="09120000302")

        response = self.client.post(
            self.signup_otp_url,
            {"mobile": "09120000302"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("already registered", response.data["detail"])
        send_sms.assert_not_called()

    @patch("accounts.views.send_sms", return_value=True)
    def test_signup_otp_request_is_rate_limited_by_cooldown(self, send_sms):
        first = self.client.post(
            self.signup_otp_url,
            {"mobile": "09120000303"},
            format="json",
        )
        second = self.client.post(
            self.signup_otp_url,
            {"mobile": "09120000303"},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS, second.data)
        self.assertIn("Please wait", second.data["detail"])
        send_sms.assert_called_once()

    @patch("accounts.views.send_sms", return_value=False)
    def test_signup_otp_request_reports_sms_failure_without_returning_code(self, send_sms):
        response = self.client.post(
            self.signup_otp_url,
            {"mobile": "09120000304"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, response.data)
        self.assertNotIn("code", str(response.data).lower())
        send_sms.assert_called_once()

    def test_register_with_valid_signup_otp_creates_user_consumes_otp_and_sanitizes_response(self):
        code = PhoneOTP.request_otp(
            mobile="09120000310",
            purpose=PhoneOTP.Purpose.SIGNUP,
        )

        response = self.client.post(
            self.signup_url,
            {
                "username": "newuser",
                "mobile": "09120000310",
                "password": TEST_PASSWORD,
                "otp_code": code,
                "email": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["username"], "newuser")
        self.assertEqual(response.data["mobile"], "09120000310")
        self.assertNotIn("password", response.data)
        self.assertNotIn("otp_code", response.data)
        self.assertNotIn("code_hash", str(response.data))

        User = get_user_model()
        user = User.objects.get(username="newuser")
        self.assertTrue(user.check_password(TEST_PASSWORD))
        otp = PhoneOTP.objects.get(mobile="09120000310", purpose=PhoneOTP.Purpose.SIGNUP)
        self.assertTrue(otp.is_used)

    def test_register_rejects_wrong_otp_and_does_not_create_user(self):
        PhoneOTP.request_otp(
            mobile="09120000311",
            purpose=PhoneOTP.Purpose.SIGNUP,
        )

        response = self.client.post(
            self.signup_url,
            {
                "username": "badotpuser",
                "mobile": "09120000311",
                "password": TEST_PASSWORD,
                "otp_code": "000000",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("otp_code", str(response.data))
        User = get_user_model()
        self.assertFalse(User.objects.filter(username="badotpuser").exists())
        otp = PhoneOTP.objects.get(mobile="09120000311", purpose=PhoneOTP.Purpose.SIGNUP)
        self.assertEqual(otp.failed_attempts, 1)

    def test_register_rejects_invalid_input_before_user_creation(self):
        invalid_cases = [
            {
                "username": "<script>alert(1)</script>",
                "mobile": "09120000320",
                "password": TEST_PASSWORD,
                "otp_code": "123456",
            },
            {
                "username": "validuser",
                "mobile": "0912abc0321",
                "password": TEST_PASSWORD,
                "otp_code": "123456",
            },
            {
                "username": "validuser2",
                "mobile": "09120000322",
                "password": "short",
                "otp_code": "123456",
            },
            {
                "username": "validuser3",
                "mobile": "09120000323",
                "password": TEST_PASSWORD,
                "otp_code": "abc123",
            },
            {
                "username": "validuser4",
                "mobile": "09120000324",
                "password": TEST_PASSWORD,
                "otp_code": "123456",
                "email": "   ",
            },
        ]

        User = get_user_model()
        for payload in invalid_cases:
            with self.subTest(payload=payload):
                response = self.client.post(self.signup_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
                self.assertFalse(User.objects.filter(username=payload["username"]).exists())

    def test_register_rejects_duplicate_username_case_insensitive(self):
        create_user(username="Duplicate", mobile="09120000330")
        code = PhoneOTP.request_otp(
            mobile="09120000331",
            purpose=PhoneOTP.Purpose.SIGNUP,
        )

        response = self.client.post(
            self.signup_url,
            {
                "username": "duplicate",
                "mobile": "09120000331",
                "password": TEST_PASSWORD,
                "otp_code": code,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("username", str(response.data).lower())

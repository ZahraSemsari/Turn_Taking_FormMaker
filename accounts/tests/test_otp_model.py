from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import PhoneOTP

from ._auth_test_utils import FAST_PASSWORD_HASHERS


@override_settings(PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class PhoneOTPModelSecurityTests(TestCase):
    def test_request_otp_returns_six_digit_code_and_stores_hash_only(self):
        code = PhoneOTP.request_otp(
            mobile="09120000200",
            purpose=PhoneOTP.Purpose.SIGNUP,
            cooldown_seconds=60,
        )
        otp = PhoneOTP.objects.get(mobile="09120000200", purpose=PhoneOTP.Purpose.SIGNUP)

        self.assertRegex(code, r"^\d{6}$")
        self.assertNotEqual(otp.code_hash, code)
        self.assertTrue(check_password(code, otp.code_hash))
        self.assertFalse(otp.is_used)

    def test_correct_otp_consumes_code_and_prevents_reuse(self):
        code = PhoneOTP.request_otp(
            mobile="09120000201",
            purpose=PhoneOTP.Purpose.SIGNUP,
        )

        first_try = PhoneOTP.verify_otp(
            mobile="09120000201",
            purpose=PhoneOTP.Purpose.SIGNUP,
            code=code,
        )
        second_try = PhoneOTP.verify_otp(
            mobile="09120000201",
            purpose=PhoneOTP.Purpose.SIGNUP,
            code=code,
        )

        self.assertTrue(first_try)
        self.assertFalse(second_try)
        otp = PhoneOTP.objects.get(mobile="09120000201", purpose=PhoneOTP.Purpose.SIGNUP)
        self.assertTrue(otp.is_used)

    def test_wrong_attempts_increment_then_lock_and_invalidate_otp(self):
        PhoneOTP.request_otp(
            mobile="09120000202",
            purpose=PhoneOTP.Purpose.SIGNUP,
        )

        first_wrong = PhoneOTP.verify_otp(
            mobile="09120000202",
            purpose=PhoneOTP.Purpose.SIGNUP,
            code="000000",
            max_attempts=2,
            lock_minutes=10,
        )
        otp_after_first = PhoneOTP.objects.get(mobile="09120000202", purpose=PhoneOTP.Purpose.SIGNUP)

        second_wrong = PhoneOTP.verify_otp(
            mobile="09120000202",
            purpose=PhoneOTP.Purpose.SIGNUP,
            code="111111",
            max_attempts=2,
            lock_minutes=10,
        )
        otp_after_second = PhoneOTP.objects.get(mobile="09120000202", purpose=PhoneOTP.Purpose.SIGNUP)

        self.assertFalse(first_wrong)
        self.assertEqual(otp_after_first.failed_attempts, 1)
        self.assertFalse(second_wrong)
        self.assertEqual(otp_after_second.failed_attempts, 2)
        self.assertTrue(otp_after_second.is_used)
        self.assertIsNotNone(otp_after_second.locked_until)
        self.assertGreater(otp_after_second.locked_until, timezone.now())

    def test_request_otp_enforces_cooldown(self):
        PhoneOTP.request_otp(
            mobile="09120000203",
            purpose=PhoneOTP.Purpose.SIGNUP,
            cooldown_seconds=60,
        )

        with self.assertRaisesRegex(ValueError, r"^cooldown:"):
            PhoneOTP.request_otp(
                mobile="09120000203",
                purpose=PhoneOTP.Purpose.SIGNUP,
                cooldown_seconds=60,
            )

    def test_new_otp_after_cooldown_invalidates_previous_unused_otp(self):
        first_code = PhoneOTP.request_otp(
            mobile="09120000204",
            purpose=PhoneOTP.Purpose.SIGNUP,
            cooldown_seconds=60,
        )
        first_otp = PhoneOTP.objects.get(mobile="09120000204", purpose=PhoneOTP.Purpose.SIGNUP)
        PhoneOTP.objects.filter(pk=first_otp.pk).update(
            created_at=timezone.now() - timedelta(seconds=120)
        )

        second_code = PhoneOTP.request_otp(
            mobile="09120000204",
            purpose=PhoneOTP.Purpose.SIGNUP,
            cooldown_seconds=60,
        )

        first_otp.refresh_from_db()
        self.assertTrue(first_otp.is_used)
        self.assertFalse(
            PhoneOTP.verify_otp(
                mobile="09120000204",
                purpose=PhoneOTP.Purpose.SIGNUP,
                code=first_code,
            )
        )
        self.assertTrue(
            PhoneOTP.verify_otp(
                mobile="09120000204",
                purpose=PhoneOTP.Purpose.SIGNUP,
                code=second_code,
            )
        )

    def test_expired_otp_is_not_accepted(self):
        code = PhoneOTP.request_otp(
            mobile="09120000205",
            purpose=PhoneOTP.Purpose.SIGNUP,
            minutes=5,
        )
        PhoneOTP.objects.filter(mobile="09120000205").update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        self.assertFalse(
            PhoneOTP.verify_otp(
                mobile="09120000205",
                purpose=PhoneOTP.Purpose.SIGNUP,
                code=code,
            )
        )

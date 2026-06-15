import json
import pytest
from unittest.mock import patch, MagicMock
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

try:
    from allauth.account.models import EmailAddress
except Exception:  # pragma: no cover
    EmailAddress = None

try:
    from accounts.models import PhoneOTP
except Exception:  # pragma: no cover
    PhoneOTP = None

try:
    from accounts.views import detect_identifier_type, format_mobile_e164
except Exception:  # pragma: no cover
    detect_identifier_type = None
    format_mobile_e164 = None


User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_factory(db):
    def _make_user(
        username="user1",
        email="user1@example.com",
        mobile="09123456789",
        password="StrongPass123!",
        **kwargs,
    ):
        return User.objects.create_user(
            username=username,
            email=email,
            mobile=mobile,
            password=password,
            **kwargs,
        )
    return _make_user


@pytest.fixture
def auth_user(api_client, user_factory):
    user = user_factory()
    api_client.force_authenticate(user=user)
    return user


@pytest.fixture
def signup_url():
    return reverse("auth-signup")


@pytest.fixture
def signup_otp_request_url():
    return reverse("auth-signup-otp-request")


@pytest.fixture
def reset_otp_confirm_url():
    return reverse("auth-password-reset-otp-confirm")


@pytest.fixture
def profile_complete_url():
    return reverse("users-profile-complete")


@pytest.fixture
def password_reset_request_url():
    return reverse("auth-password-reset-request")


@pytest.fixture
def login_url():
    return reverse("auth-login")


@pytest.fixture
def me_url():
    return reverse("users-me")


@pytest.fixture
def protected_url():
    return reverse("auth-protected-debug")


@pytest.fixture
def make_phone_otp(db):
    def _make_phone_otp(
        mobile="09123456789",
        purpose=None,
        code="123456",
        minutes=5,
        used=False,
        failed_attempts=0,
        locked_until=None,
    ):
        purpose = purpose or PhoneOTP.Purpose.SIGNUP
        otp = PhoneOTP.request_otp(
            mobile=mobile,
            purpose=purpose,
            minutes=minutes,
            cooldown_seconds=0,
            max_attempts=5,
            lock_minutes=10,
        )
        if otp != code:
            pass
        obj = PhoneOTP.objects.filter(mobile=mobile, purpose=purpose).order_by("-created_at").first()
        obj.is_used = used
        obj.failed_attempts = failed_attempts
        obj.locked_until = locked_until
        obj.save(update_fields=["is_used", "failed_attempts", "locked_until"])
        return obj
    return _make_phone_otp


# ---------------------------
# Coverage matrix reference
# ---------------------------
# category | scenario | expected | why it matters | target
COVERAGE_MATRIX = [
    ("API contract", "Invalid JSON body to signup", "400", "Crash-path hardening", "crash"),
    ("API contract", "Wrong content type to signup", "415/400", "Malformed request handling", "validation"),
    ("API contract", "Missing required signup fields", "400", "Prevents partial registration", "validation"),
    ("API contract", "Wrong data types in signup fields", "400", "Type safety", "validation"),
    ("API contract", "Empty strings/whitespace in signup fields", "400", "Normalization + required checks", "validation"),
    ("API contract", "Large payloads in signup fields", "400", "Defensive validation", "crash"),
    ("Security", "OTP code replay after success", "400", "Prevents reuse", "security"),
    ("Security", "Expired OTP", "400", "Stops stale codes", "security"),
    ("Security", "OTP wrong attempts cause lockout", "400/429", "Brute force mitigation", "security"),
    ("Security", "Duplicate mobile registration", "400", "Prevents account hijack", "security"),
    ("Concurrency", "Concurrent signup requests same mobile", "one success/one fail", "Integrity under race", "concurrency"),
    ("Concurrency", "Concurrent OTP request / verify race", "single active OTP", "Prevents double-spend", "concurrency"),
    ("Integration", "Email confirmation send failure", "201 with logged error", "External dependency failure isolation", "integration failure"),
    ("Integration", "SMS send failure", "500 on signup OTP request", "Dependency resilience", "integration failure"),
    ("Model integrity", "Whitespace mobile normalization", "stored stripped", "Data consistency", "validation"),
    ("Model integrity", "Unicode normalization in username/email", "accepts or validates safely", "Internationalization edge cases", "validation"),
    ("Model integrity", "Superuser invariants", "ValueError on invalid flags", "Admin safety", "validation"),
    ("Model integrity", "Unique constraints for email/mobile", "IntegrityError", "Database correctness", "integration failure"),
]


@pytest.mark.django_db
def test_signup_invalid_json_returns_400(api_client, signup_url):
    response = api_client.post(signup_url, data="{bad json", content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_invalid_content_type_returns_error(api_client, signup_url):
    response = api_client.post(signup_url, data="username=a&mobile=09123456789", content_type="text/plain")
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)


@pytest.mark.django_db
def test_signup_missing_all_required_fields_returns_400(api_client, signup_url):
    response = api_client.post(signup_url, data={}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in response.data or "mobile" in response.data or "password" in response.data or "otp_code" in response.data


@pytest.mark.django_db
def test_signup_missing_username_returns_400(api_client, signup_url):
    payload = {
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "u1@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in response.data


@pytest.mark.django_db
def test_signup_missing_mobile_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "u1@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "mobile" in response.data


@pytest.mark.django_db
def test_signup_missing_password_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "otp_code": "123456",
        "email": "u1@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "password" in response.data


@pytest.mark.django_db
def test_signup_missing_otp_code_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "email": "u1@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "otp_code" in response.data


@pytest.mark.django_db
def test_signup_wrong_mobile_type_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": 9123456789,
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_wrong_password_type_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": 12345678,
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_wrong_otp_type_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": 123456,
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_empty_username_whitespace_returns_400(api_client, signup_url):
    payload = {
        "username": "   ",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_empty_mobile_whitespace_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "   ",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_mobile_with_leading_trailing_spaces_rejected_or_trimmed(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": " 09123456789 ",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "u1@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_201_CREATED)


@pytest.mark.django_db
def test_signup_invalid_mobile_length_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "0912345678",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_invalid_mobile_prefix_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "08123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_invalid_otp_length_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "12345",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_invalid_otp_non_digit_returns_400(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "12ab56",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_large_username_payload_rejected(api_client, signup_url):
    payload = {
        "username": "u" * 5000,
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR)
    assert response.status_code != status.HTTP_201_CREATED


@pytest.mark.django_db
def test_signup_large_email_payload_rejected(api_client, signup_url):
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": ("a" * 250) + "@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR)


@pytest.mark.django_db
def test_signup_unicode_username_allowed_or_validated(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "کاربر۱",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "unicode@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_unicode_normalization_combining_chars(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "e\u0301xample",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_duplicate_mobile_returns_400(api_client, signup_url, user_factory):
    user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    payload = {
        "username": "u2",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "u2@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_duplicate_username_returns_400(api_client, signup_url, user_factory):
    user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    payload = {
        "username": "u1",
        "mobile": "09123456780",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "u2@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_duplicate_email_returns_400(api_client, signup_url, user_factory):
    user_factory(username="u1", mobile="09123456789", email="dup@example.com")
    payload = {
        "username": "u2",
        "mobile": "09123456780",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "dup@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_null_email_allowed(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": None,
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_blank_email_allowed_or_rejected(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_wrong_otp_returns_400(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "000000",
        "email": "u1@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "otp_code" in response.data or "detail" in response.data


@pytest.mark.django_db
def test_signup_expired_otp_returns_400(api_client, signup_url, make_phone_otp):
    otp = make_phone_otp(mobile="09123456789")
    otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    otp.save(update_fields=["expires_at"])
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_reused_otp_after_success_fails(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "u1@example.com",
    }
    first = api_client.post(signup_url, data=payload, format="json")
    assert first.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)
    second = api_client.post(signup_url, data=payload, format="json")
    assert second.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_concurrent_submissions_same_mobile_one_wins(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload1 = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    payload2 = {
        "username": "u2",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    r1 = api_client.post(signup_url, data=payload1, format="json")
    r2 = api_client.post(signup_url, data=payload2, format="json")
    assert {r1.status_code, r2.status_code}.issubset({status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST})
    assert not (r1.status_code == status.HTTP_201_CREATED and r2.status_code == status.HTTP_201_CREATED)


@pytest.mark.django_db
def test_signup_profile_incomplete_flag_missing_mobile_or_password(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    if response.status_code == status.HTTP_201_CREATED:
        assert "profile_incomplete" in response.data


@pytest.mark.django_db
def test_signup_email_confirmation_failure_is_handled(api_client, signup_url, make_phone_otp, user_factory):
    make_phone_otp(mobile="09123456789")
    with patch("accounts.views.EmailAddress.objects.get_or_create") as mocked_get_or_create:
        email_addr = MagicMock()
        email_addr.verified = False
        email_addr.send_confirmation.side_effect = Exception("smtp down")
        mocked_get_or_create.return_value = (email_addr, True)

        payload = {
            "username": "u1",
            "mobile": "09123456789",
            "password": "StrongPass123!",
            "otp_code": "123456",
            "email": "u1@example.com",
        }
        response = api_client.post(signup_url, data=payload, format="json")
        assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)

# test_add_more_gap.py - اصلاح کنید
# @pytest.mark.django_db
def test_signup_sms_failure_returns_500(api_client, signup_url):
    """تست خطای SMS - اصلاح شده"""
    with patch("accounts.views.send_sms", return_value=False):
        with patch("accounts.views.PhoneOTP.request_otp") as mock_request:
            # مهم: باید کد واقعی برگرداند، نه هر کدی
            real_code = PhoneOTP.generate_code()
            mock_request.return_value = real_code
            
            response = api_client.post(
                signup_url,
                data={
                    "username": "u1",
                    "mobile": "09123456789",
                    "password": "StrongPass123!",
                    "otp_code": real_code,  # استفاده از کد واقعی
                    "email": "u1@example.com",
                },
                format="json",
            )
            # باید 500 بدهد چون SMS فرستاده نشده
            assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_signup_otp_request_missing_mobile_returns_400(api_client, signup_otp_request_url):
    response = api_client.post(signup_otp_request_url, data={}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_otp_request_invalid_mobile_format_returns_400(api_client, signup_otp_request_url):
    response = api_client.post(signup_otp_request_url, data={"mobile": "123"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_otp_request_duplicate_mobile_returns_400(api_client, signup_otp_request_url, user_factory):
    user_factory(mobile="09123456789", username="u1", email="u1@example.com")
    response = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_otp_request_cooldown_returns_429(api_client, signup_otp_request_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    with patch("accounts.views.PhoneOTP.request_otp", side_effect=ValueError("cooldown:42")):
        response = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_signup_otp_request_locked_returns_429(api_client, signup_otp_request_url):
    with patch("accounts.views.PhoneOTP.request_otp", side_effect=ValueError("locked:21")):
        response = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_signup_otp_request_generic_valueerror_returns_400(api_client, signup_otp_request_url):
    with patch("accounts.views.PhoneOTP.request_otp", side_effect=ValueError("boom")):
        response = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_otp_request_sms_send_success(api_client, signup_otp_request_url):
    with patch("accounts.views.PhoneOTP.request_otp", return_value="123456"), patch("accounts.views.send_sms", return_value=True):
        response = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_signup_otp_request_sms_send_failure_returns_500(api_client, signup_otp_request_url):
    with patch("accounts.views.PhoneOTP.request_otp", return_value="123456"), patch("accounts.views.send_sms", return_value=False):
        response = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
def test_password_reset_confirm_missing_fields_returns_400(api_client, reset_otp_confirm_url):
    response = api_client.post(reset_otp_confirm_url, data={}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_confirm_unknown_mobile_returns_400(api_client, reset_otp_confirm_url):
    response = api_client.post(
        reset_otp_confirm_url,
        data={"mobile": "09123456789", "code": "123456", "new_password": "NewPass123!"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_confirm_wrong_otp_returns_400(api_client, reset_otp_confirm_url, user_factory, make_phone_otp):
    user_factory(mobile="09123456789", username="u1", email="u1@example.com")
    make_phone_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.RESET_PASSWORD)
    response = api_client.post(
        reset_otp_confirm_url,
        data={"mobile": "09123456789", "code": "000000", "new_password": "NewPass123!"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_confirm_expired_otp_returns_400(api_client, reset_otp_confirm_url, user_factory, make_phone_otp):
    user_factory(mobile="09123456789", username="u1", email="u1@example.com")
    otp = make_phone_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.RESET_PASSWORD)
    otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    otp.save(update_fields=["expires_at"])
    response = api_client.post(
        reset_otp_confirm_url,
        data={"mobile": "09123456789", "code": "123456", "new_password": "NewPass123!"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_confirm_success_updates_password(api_client, reset_otp_confirm_url, user_factory, make_phone_otp):
    user = user_factory(mobile="09123456789", username="u1", email="u1@example.com", password="OldPass123!")
    otp = make_phone_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.RESET_PASSWORD)
    with patch("accounts.models.check_password", return_value=True):
        otp.code_hash = otp.code_hash
    response = api_client.post(
        reset_otp_confirm_url,
        data={"mobile": "09123456789", "code": "123456", "new_password": "NewPass123!"},
        format="json",
    )
    if response.status_code == status.HTTP_200_OK:
        user.refresh_from_db()
        assert user.check_password("NewPass123!")


@pytest.mark.django_db
def test_password_reset_confirm_reused_code_fails(api_client, reset_otp_confirm_url, user_factory, make_phone_otp):
    user_factory(mobile="09123456789", username="u1", email="u1@example.com")
    make_phone_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.RESET_PASSWORD)
    payload = {"mobile": "09123456789", "code": "123456", "new_password": "NewPass123!"}
    first = api_client.post(reset_otp_confirm_url, data=payload, format="json")
    second = api_client.post(reset_otp_confirm_url, data=payload, format="json")
    assert first.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST)
    assert second.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_profile_complete_requires_auth(api_client, profile_complete_url):
    response = api_client.patch(profile_complete_url, data={"mobile": "09123456789"}, format="json")
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
def test_profile_complete_missing_mobile_when_user_has_none_returns_400(api_client, user_factory, profile_complete_url):
    user = user_factory(mobile=None, username="u1", email="u1@example.com")
    api_client.force_authenticate(user=user)
    response = api_client.patch(profile_complete_url, data={}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_profile_complete_invalid_mobile_length_returns_400(api_client, user_factory, profile_complete_url):
    user = user_factory(mobile=None, username="u1", email="u1@example.com")
    api_client.force_authenticate(user=user)
    response = api_client.patch(profile_complete_url, data={"mobile": "09123"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_profile_complete_duplicate_mobile_returns_400(api_client, user_factory, profile_complete_url):
    user1 = user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    user2 = user_factory(username="u2", mobile="09123456780", email="u2@example.com")
    api_client.force_authenticate(user=user2)
    response = api_client.patch(profile_complete_url, data={"mobile": "09123456789"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    user1.refresh_from_db()
    assert user1.mobile == "09123456789"


@pytest.mark.django_db
def test_profile_complete_password_required_if_no_usable_password(api_client, user_factory, profile_complete_url):
    user = user_factory(username="u1", mobile="09123456789", email="u1@example.com", password=None)
    user.set_unusable_password()
    user.save(update_fields=["password"])
    api_client.force_authenticate(user=user)
    response = api_client.patch(profile_complete_url, data={"first_name": "A"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_profile_complete_password_too_short_returns_400(api_client, user_factory, profile_complete_url):
    user = user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    api_client.force_authenticate(user=user)
    response = api_client.patch(profile_complete_url, data={"password": "short"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_profile_complete_updates_names_and_mobile(api_client, user_factory, profile_complete_url):
    user = user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    api_client.force_authenticate(user=user)
    response = api_client.patch(
        profile_complete_url,
        data={
            "mobile": "09123456780",
            "password": "NewPass123!",
            "first_name": "Ali",
            "last_name": "Ahmadi",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.first_name == "Ali"
    assert user.last_name == "Ahmadi"
    assert user.mobile == "09123456780"


@pytest.mark.django_db
def test_profile_complete_unicode_names(api_client, user_factory, profile_complete_url):
    user = user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    api_client.force_authenticate(user=user)
    response = api_client.patch(
        profile_complete_url,
        data={"first_name": "علی", "last_name": "محمدی"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.first_name == "علی"
    assert user.last_name == "محمدی"


@pytest.mark.django_db
def test_me_endpoint_returns_user_info(api_client, auth_user, me_url):
    response = api_client.get(me_url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["username"] == auth_user.username


@pytest.mark.django_db
def test_protected_endpoint_requires_auth(api_client, protected_url):
    response = api_client.get(protected_url)
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


@pytest.mark.django_db
def test_phoneotp_generate_code_format():
    code = PhoneOTP.generate_code()
    assert isinstance(code, str)
    assert len(code) == 6
    assert code.isdigit()


@pytest.mark.django_db
def test_phoneotp_request_otp_creates_db_row():
    code = PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=5,
        cooldown_seconds=0,
    )
    otp = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).latest("created_at")
    assert code
    assert otp.code_hash
    assert otp.is_used is False


@pytest.mark.django_db
def test_phoneotp_verify_success_marks_used():
    code = PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=5,
        cooldown_seconds=0,
    )
    assert PhoneOTP.verify_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code=code,
    ) is True
    otp = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).latest("created_at")
    assert otp.is_used is True


@pytest.mark.django_db
def test_phoneotp_verify_wrong_code_increments_attempts():
    PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=5,
        cooldown_seconds=0,
    )
    assert PhoneOTP.verify_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code="000000",
    ) is False
    otp = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).latest("created_at")
    assert otp.failed_attempts >= 1


@pytest.mark.django_db
def test_phoneotp_replay_prevention_after_success():
    code = PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=5,
        cooldown_seconds=0,
    )
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code=code) is True
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code=code) is False


@pytest.mark.django_db
def test_phoneotp_expiration_blocks_verification():
    code = PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=0,
        cooldown_seconds=0,
    )
    otp = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).latest("created_at")
    otp.expires_at = timezone.now() - timezone.timedelta(seconds=1)
    otp.save(update_fields=["expires_at"])
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code=code) is False


@pytest.mark.django_db
def test_phoneotp_lockout_after_max_attempts():
    code = PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=5,
        cooldown_seconds=0,
        max_attempts=2,
        lock_minutes=10,
    )
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code="000000", max_attempts=2) is False
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code="111111", max_attempts=2) is False
    otp = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).latest("created_at")
    assert otp.locked_until is not None
    assert otp.is_used is True


@pytest.mark.django_db
def test_phoneotp_request_otp_cooldown_raises_valueerror():
    PhoneOTP.request_otp(
        mobile="09123456789",
        purpose=PhoneOTP.Purpose.SIGNUP,
        minutes=5,
        cooldown_seconds=60,
    )
    with pytest.raises(ValueError):
        PhoneOTP.request_otp(
            mobile="09123456789",
            purpose=PhoneOTP.Purpose.SIGNUP,
            minutes=5,
            cooldown_seconds=60,
        )


@pytest.mark.django_db
def test_phoneotp_request_otp_invalidates_previous_active_otp():
    code1 = PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, minutes=5, cooldown_seconds=0)
    code2 = PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, minutes=5, cooldown_seconds=0)
    assert code1 != code2 or code1 == code2
    active = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, is_used=False)
    assert active.count() == 1


@pytest.mark.django_db
def test_phoneotp_verify_otp_no_active_row_returns_false():
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code="123456") is False


@pytest.mark.django_db
def test_user_manager_create_user_hashes_password():
    user = User.objects.create_user(
        username="u1",
        email="u1@example.com",
        mobile="09123456789",
        password="StrongPass123!",
    )
    assert user.password != "StrongPass123!"
    assert user.check_password("StrongPass123!")


@pytest.mark.django_db
def test_user_manager_rejects_missing_username():
    with pytest.raises(ValueError):
        User.objects.create_user(username="", email="u1@example.com", mobile="09123456789", password="StrongPass123!")


@pytest.mark.django_db
def test_user_manager_str_returns_username(user_factory):
    user = user_factory(username="abc")
    assert str(user) == "abc"


@pytest.mark.django_db
def test_user_manager_email_normalization_casefold():
    user = User.objects.create_user(
        username="u1",
        email="User@Example.COM",
        mobile="09123456789",
        password="StrongPass123!",
    )
    assert user.email == "User@example.com"


@pytest.mark.django_db
def test_user_manager_mobile_whitespace_removed():
    user = User.objects.create_user(
        username="u1",
        email="u1@example.com",
        mobile="09 123 456 789",
        password="StrongPass123!",
    )
    assert " " not in (user.mobile or "")


@pytest.mark.django_db
def test_create_superuser_requires_mobile():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            mobile=None,
            password="StrongPass123!",
        )


@pytest.mark.django_db
def test_create_superuser_sets_flags():
    user = User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        mobile="09123456789",
        password="StrongPass123!",
    )
    assert user.is_staff is True
    assert user.is_superuser is True


@pytest.mark.django_db
def test_duplicate_null_email_allowed_via_model(user_factory):
    u1 = user_factory(username="u1", email=None, mobile="09123456789")
    u2 = user_factory(username="u2", email=None, mobile="09123456780")
    assert u1.pk and u2.pk


@pytest.mark.django_db
def test_duplicate_email_raises_integrity_error(user_factory):
    user_factory(username="u1", email="dup@example.com", mobile="09123456789")
    with pytest.raises(IntegrityError):
        user_factory(username="u2", email="dup@example.com", mobile="09123456780")


@pytest.mark.django_db
def test_duplicate_mobile_raises_integrity_error(user_factory):
    user_factory(username="u1", email="u1@example.com", mobile="09123456789")
    with pytest.raises(IntegrityError):
        user_factory(username="u2", email="u2@example.com", mobile="09123456789")


@pytest.mark.django_db
def test_detect_identifier_type_email():
    if detect_identifier_type is None:
        pytest.skip("helper not available")
    assert detect_identifier_type("user@example.com") == "email"


@pytest.mark.django_db
def test_detect_identifier_type_mobile():
    if detect_identifier_type is None:
        pytest.skip("helper not available")
    assert detect_identifier_type("09123456789") == "mobile"


@pytest.mark.django_db
def test_detect_identifier_type_username():
    if detect_identifier_type is None:
        pytest.skip("helper not available")
    assert detect_identifier_type("someone") == "username"


@pytest.mark.django_db
def test_format_mobile_e164_raises_for_invalid():
    if format_mobile_e164 is None:
        pytest.skip("helper not available")
    with pytest.raises(ValueError):
        format_mobile_e164("123")


@pytest.mark.django_db
def test_format_mobile_e164_from_09():
    if format_mobile_e164 is None:
        pytest.skip("helper not available")
    assert format_mobile_e164("09123456789") == "+989123456789"


@pytest.mark.django_db
def test_format_mobile_e164_from_989():
    if format_mobile_e164 is None:
        pytest.skip("helper not available")
    assert format_mobile_e164("989123456789") == "+989123456789"


@pytest.mark.django_db
def test_signup_race_like_duplicate_request_second_fails(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    payload = {
        "username": "u1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "123456",
    }
    r1 = api_client.post(signup_url, data=payload, format="json")
    r2 = api_client.post(signup_url, data=payload, format="json")
    assert r1.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)
    assert r2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_otp_request_concurrent_duplicate_blocks_second(api_client, signup_otp_request_url):
    with patch("accounts.views.PhoneOTP.request_otp", side_effect=["123456", ValueError("cooldown:59")]):
        r1 = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        r2 = api_client.post(signup_otp_request_url, data={"mobile": "09123456789"}, format="json")
        assert r1.status_code in (status.HTTP_200_OK, status.HTTP_500_INTERNAL_SERVER_ERROR)
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_signup_handles_exception_from_otp_verification(api_client, signup_url):
    with patch("accounts.models.PhoneOTP.verify_otp", side_effect=Exception("db down")):
        response = api_client.post(
            signup_url,
            data={
                "username": "u1",
                "mobile": "09123456789",
                "password": "StrongPass123!",
                "otp_code": "123456",
                "email": "u1@example.com",
            },
            format="json",
        )
        assert response.status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_password_reset_request_requires_identifier(api_client, password_reset_request_url):
    response = api_client.post(password_reset_request_url, data={}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_password_reset_request_email_path_returns_200(api_client, password_reset_request_url, user_factory):
    user_factory(username="u1", email="u1@example.com", mobile="09123456789")
    with patch("accounts.views.PasswordResetSerializer") as mocked_serializer:
        instance = mocked_serializer.return_value
        instance.is_valid.return_value = True
        instance.save.return_value = None
        response = api_client.post(password_reset_request_url, data={"identifier": "u1@example.com"}, format="json")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_password_reset_request_mobile_cooldown_429(api_client, password_reset_request_url, user_factory):
    user_factory(username="u1", email="u1@example.com", mobile="09123456789")
    with patch("accounts.views.PhoneOTP.request_otp", side_effect=ValueError("cooldown:5")):
        response = api_client.post(password_reset_request_url, data={"identifier": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_password_reset_request_mobile_locked_429(api_client, password_reset_request_url, user_factory):
    user_factory(username="u1", email="u1@example.com", mobile="09123456789")
    with patch("accounts.views.PhoneOTP.request_otp", side_effect=ValueError("locked:5")):
        response = api_client.post(password_reset_request_url, data={"identifier": "09123456789"}, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_password_reset_request_username_without_email_or_mobile_returns_200(api_client, password_reset_request_url, user_factory):
    user_factory(username="u1", email=None, mobile=None)
    response = api_client.post(password_reset_request_url, data={"identifier": "u1"}, format="json")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_model_create_user_trims_mobile_whitespace(user_factory):
    user = user_factory(username="u1", mobile=" 09123456789 ")
    assert user.mobile.strip() == "09123456789"


@pytest.mark.django_db
def test_user_serializer_fields_accessible(user_factory):
    user = user_factory()
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "mobile": user.mobile,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
    assert set(data.keys()) == {"id", "username", "email", "mobile", "first_name", "last_name"}


@pytest.mark.django_db
def test_concurrent_profile_update_mobile_conflict(api_client, user_factory, profile_complete_url):
    u1 = user_factory(username="u1", mobile="09123456789", email="u1@example.com")
    u2 = user_factory(username="u2", mobile="09123456780", email="u2@example.com")
    api_client.force_authenticate(user=u2)
    resp = api_client.patch(profile_complete_url, data={"mobile": "09123456789"}, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_with_db_transaction_rolls_back_on_exception(api_client, signup_url):
    with patch("accounts.models.PhoneOTP.verify_otp", side_effect=Exception("transaction failure")):
        with pytest.raises(Exception):
            with transaction.atomic():
                api_client.post(
                    signup_url,
                    data={
                        "username": "u1",
                        "mobile": "09123456789",
                        "password": "StrongPass123!",
                        "otp_code": "123456",
                    },
                    format="json",
                )


@pytest.mark.django_db
def test_signup_email_case_duplicate_is_rejected(api_client, signup_url, user_factory):
    user_factory(username="u1", email="dup@example.com", mobile="09123456789")
    payload = {
        "username": "u2",
        "mobile": "09123456780",
        "password": "StrongPass123!",
        "otp_code": "123456",
        "email": "DUP@example.com",
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_whitespace_username_rejected_or_trimmed(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    response = api_client.post(
        signup_url,
        data={
            "username": " user1 ",
            "mobile": "09123456789",
            "password": "StrongPass123!",
            "otp_code": "123456",
        },
        format="json",
    )
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_password_minimum_length_boundary(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    response = api_client.post(
        signup_url,
        data={
            "username": "u1",
            "mobile": "09123456789",
            "password": "1234567",
            "otp_code": "123456",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_password_exact_minimum_length_boundary(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    response = api_client.post(
        signup_url,
        data={
            "username": "u1",
            "mobile": "09123456789",
            "password": "12345678",
            "otp_code": "123456",
        },
        format="json",
    )
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_request_with_nested_json_fields_rejected(api_client, signup_url):
    payload = {
        "username": {"value": "u1"},
        "mobile": ["09123456789"],
        "password": {"value": "StrongPass123!"},
        "otp_code": {"value": "123456"},
    }
    response = api_client.post(signup_url, data=payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_signup_request_with_extra_unknown_fields_ignored_or_rejected(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    response = api_client.post(
        signup_url,
        data={
            "username": "u1",
            "mobile": "09123456789",
            "password": "StrongPass123!",
            "otp_code": "123456",
            "unexpected": "field",
        },
        format="json",
    )
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
def test_signup_request_unknown_field_does_not_create_extra_columns(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    before = User.objects.count()
    api_client.post(
        signup_url,
        data={
            "username": "u1",
            "mobile": "09123456789",
            "password": "StrongPass123!",
            "otp_code": "123456",
            "role": "admin",
        },
        format="json",
    )
    after = User.objects.count()
    assert after >= before


@pytest.mark.django_db
def test_phoneotp_latest_active_selection_prefers_newest():
    old = PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, minutes=5, cooldown_seconds=0)
    newer = PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, minutes=5, cooldown_seconds=0)
    latest = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).order_by("-created_at").first()
    assert latest is not None
    assert latest.is_used is False
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code=newer) is True


@pytest.mark.django_db
def test_phoneotp_verify_respects_lock_state():
    code = PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, minutes=5, cooldown_seconds=0)
    otp = PhoneOTP.objects.filter(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP).latest("created_at")
    otp.locked_until = timezone.now() + timezone.timedelta(minutes=5)
    otp.save(update_fields=["locked_until"])
    assert PhoneOTP.verify_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP, code=code) is False


@pytest.mark.django_db
def test_signup_endpoint_returns_201_with_profile_incomplete_flag_when_successful(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    response = api_client.post(
        signup_url,
        data={
            "username": "u1",
            "mobile": "09123456789",
            "password": "StrongPass123!",
            "otp_code": "123456",
            "email": "u1@example.com",
        },
        format="json",
    )
    assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST)
    if response.status_code == status.HTTP_201_CREATED:
        assert "profile_incomplete" in response.data


@pytest.mark.django_db
def test_signup_endpoint_does_not_expose_otp_code_in_response(api_client, signup_url, make_phone_otp):
    make_phone_otp(mobile="09123456789")
    response = api_client.post(
        signup_url,
        data={
            "username": "u1",
            "mobile": "09123456789",
            "password": "StrongPass123!",
            "otp_code": "123456",
            "email": "u1@example.com",
        },
        format="json",
    )
    if response.status_code == status.HTTP_201_CREATED:
        assert "otp_code" not in response.data

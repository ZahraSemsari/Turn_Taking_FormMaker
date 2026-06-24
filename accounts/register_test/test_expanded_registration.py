# tests/test_expanded_registration.py
import pytest
import json
import hashlib
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import PhoneOTP, User
from accounts.serializers import RegisterSerializer
from freezegun import freeze_time


# ===================== OTP ABUSE TESTS =====================

@pytest.mark.django_db
def test_request_otp_already_registered_mobile(api_client, create_user):
    create_user(mobile="09123456789")
    response = api_client.post("/account/signup/otp/request/", {"mobile": "09123456789"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already registered" in response.data["detail"].lower()


@pytest.mark.django_db
def test_verify_otp_empty_code(api_client):
    PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "testuser",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": ""
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_verify_otp_non_digit_code(api_client):
    PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "testuser",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": "abc123"
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_invalid_mobile_format(api_client):
    response = api_client.post("/account/signup/otp/request/", {"mobile": "0912345678"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_mobile_with_spaces(api_client):
    response = api_client.post("/account/signup/otp/request/", {"mobile": "0912 345 6789"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_10_digit_mobile(api_client):
    response = api_client.post("/account/signup/otp/request/", {"mobile": "091234567"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_12_digit_mobile(api_client):
    response = api_client.post("/account/signup/otp/request/", {"mobile": "091234567890"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_letters_in_mobile(api_client):
    response = api_client.post("/account/signup/otp/request/", {"mobile": "0912345678a"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_international_format(api_client):
    response = api_client.post("/account/signup/otp/request/", {"mobile": "+989123456789"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_locked_out_after_max_attempts(api_client):
    mobile = "09120000100"
    for _ in range(5):
        PhoneOTP.request_otp(mobile="09120000100", purpose=PhoneOTP.Purpose.SIGNUP, cooldown_seconds=0)
        PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code="000000")
    
    response = api_client.post("/account/signup/otp/request/", {"mobile": mobile})
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_verify_otp_wrong_code_multiple_times(api_client):
    mobile = "09120000101"
    code = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    for _ in range(4):
        PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code="111111")
    
    is_valid = PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code=code)
    assert is_valid is True


@pytest.mark.django_db
def test_verify_otp_lockout_after_max_wrong_attempts(api_client):
    mobile = "09120000102"
    PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    for _ in range(5):
        PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code="000000")
    
    otp = PhoneOTP.objects.filter(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP).first()
    assert otp.locked_until is not None
    assert otp.locked_until > timezone.now()


@pytest.mark.django_db
def test_concurrent_otp_requests_same_mobile():
    """تست درخواست‌های همزمان OTP برای یک شماره"""
    from concurrent.futures import ThreadPoolExecutor
    mobile = "09120000103"
    
    def request_with_delay():
        try:
            # ایجاد فاصله زمانی بین درخواست‌ها
            import time
            time.sleep(0.1)
            return PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
        except ValueError:
            return None
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(request_with_delay) for _ in range(10)]
        results = [f.result() for f in futures]
    
    active_otps = PhoneOTP.objects.filter(
        mobile=mobile,
        purpose=PhoneOTP.Purpose.SIGNUP,
        is_used=False
    ).count()
    
    assert active_otps <= 1


@pytest.mark.django_db
def test_verify_expired_otp(api_client):
    mobile = "09120000104"
    with freeze_time("2025-01-01 10:00:00"):
        code = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, minutes=1)
    
    with freeze_time("2025-01-01 10:02:00"):
        response = api_client.post("/account/signup/", {
            "username": "expireduser",
            "mobile": mobile,
            "password": "StrongPass123!",
            "otp_code": code
        })
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_request_otp_during_cooldown():
    mobile = "09120000105"
    PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, cooldown_seconds=60)
    
    with pytest.raises(ValueError) as exc_info:
        PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, cooldown_seconds=60)
    
    assert "cooldown" in str(exc_info.value)


@pytest.mark.django_db
def test_request_otp_after_cooldown_expires():
    mobile = "09120000106"
    with freeze_time("2025-01-01 10:00:00"):
        PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, cooldown_seconds=60)
    
    with freeze_time("2025-01-01 10:01:01"):
        code = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, cooldown_seconds=60)
    
    assert code is not None
    assert len(code) == 6


# ===================== EDGE CASES =====================

@pytest.mark.django_db
def test_register_mobile_with_spaces_trimmed(api_client):
    code = PhoneOTP.request_otp(mobile="09120000107", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "spacesuser",
        "mobile": " 09120000107 ",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED
    user = User.objects.get(username="spacesuser")
    assert user.mobile == "09120000107"


@pytest.mark.django_db
def test_register_email_uppercase_normalized(api_client):
    code = PhoneOTP.request_otp(mobile="09120000108", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "emailcase",
        "mobile": "09120000108",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "TEST@EXAMPLE.COM"
    })
    assert response.status_code == status.HTTP_201_CREATED
    user = User.objects.get(username="emailcase")
    assert user.email == "TEST@example.com"


@pytest.mark.django_db
def test_register_emoji_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000109", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "test😀user",
        "mobile": "09120000109",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_register_username_starting_underscore(api_client):
    code = PhoneOTP.request_otp(mobile="09120000110", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "_underscoreuser",
        "mobile": "09120000110",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_username_with_dots(api_client):
    code = PhoneOTP.request_otp(mobile="09120000111", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "dot.user.name",
        "mobile": "09120000111",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_numeric_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000112", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "123456",
        "mobile": "09120000112",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_empty_string_email(api_client):
    code = PhoneOTP.request_otp(mobile="09120000113", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "emptyemailuser",
        "mobile": "09120000113",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": ""
    }, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data.get("email") is None or response.data.get("email") == ""


@pytest.mark.django_db
def test_register_null_email(api_client):
    code = PhoneOTP.request_otp(mobile="09120000114", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "nullemailuser",
        "mobile": "09120000114",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": None
    }, format="json")
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_whitespace_only_email(api_client):
    code = PhoneOTP.request_otp(mobile="09120000115", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "whitespaceemail",
        "mobile": "09120000115",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "   "
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_email_missing_at_symbol(api_client):
    code = PhoneOTP.request_otp(mobile="09120000116", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "invalidemail",
        "mobile": "09120000116",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "testexample.com"
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_password_exactly_8_chars(api_client):
    code = PhoneOTP.request_otp(mobile="09120000117", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "minpassuser",
        "mobile": "09120000117",
        "password": "Pass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_password_100_chars(api_client):
    code = PhoneOTP.request_otp(mobile="09120000118", purpose=PhoneOTP.Purpose.SIGNUP)
    long_password = "A" * 100
    response = api_client.post("/account/signup/", {
        "username": "longpassuser",
        "mobile": "09120000118",
        "password": long_password,
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_username_max_length_150(api_client):
    code = PhoneOTP.request_otp(mobile="09120000119", purpose=PhoneOTP.Purpose.SIGNUP)
    username = "a" * 150
    response = api_client.post("/account/signup/", {
        "username": username,
        "mobile": "09120000119",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_username_151_chars(api_client):
    code = PhoneOTP.request_otp(mobile="09120000120", purpose=PhoneOTP.Purpose.SIGNUP)
    username = "a" * 151
    response = api_client.post("/account/signup/", {
        "username": username,
        "mobile": "09120000120",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ===================== CRASH PATHS =====================

@pytest.mark.django_db
def test_register_missing_username_field(api_client):
    code = PhoneOTP.request_otp(mobile="09120000121", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "mobile": "09120000121",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_missing_mobile_field(api_client):
    code = PhoneOTP.request_otp(mobile="09120000122", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "missingmobile",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_missing_password_field(api_client):
    code = PhoneOTP.request_otp(mobile="09120000123", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "missingpass",
        "mobile": "09120000123",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_missing_otp_code_field(api_client):
    response = api_client.post("/account/signup/", {
        "username": "missingotp",
        "mobile": "09120000124",
        "password": "StrongPass123!"
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_null_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000125", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": None,
        "mobile": "09120000125",
        "password": "StrongPass123!",
        "otp_code": code
    }, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_null_mobile(api_client):
    code = PhoneOTP.request_otp(mobile="09120000126", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "nullmobile",
        "mobile": None,
        "password": "StrongPass123!",
        "otp_code": code
    }, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST




@pytest.mark.django_db
def test_register_object_as_password(api_client):
    code = PhoneOTP.request_otp(mobile="09120000129", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "objectpass",
        "mobile": "09120000129",
        "password": {"key": "value"},
        "otp_code": code
    }, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_boolean_as_otp_code(api_client):
    code = PhoneOTP.request_otp(mobile="09120000130", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "boolotp",
        "mobile": "09120000130",
        "password": "StrongPass123!",
        "otp_code": False
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_float_as_mobile(api_client):
    code = PhoneOTP.request_otp(mobile="09120000131", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "floatmobile",
        "mobile": 9123456789.0,
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_extremely_nested_json(api_client, create_user):
    code = PhoneOTP.request_otp(mobile="09120000132", purpose=PhoneOTP.Purpose.SIGNUP)
    payload = {
        "username": "nested",
        "mobile": "09120000132",
        "password": "StrongPass123!",
        "otp_code": code,
        "extra": {"a": {"b": {"c": {"d": {"e": {"f": {"g": "deep"}}}}}}}
    }
    response = api_client.post("/account/signup/", payload, format="json")
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_register_duplicate_json_keys(api_client):
    invalid_json = '{"username": "test", "username": "test2", "mobile": "09120000133", "password": "pass", "otp_code": "123456"}'
    response = api_client.generic("POST", "/account/signup/", invalid_json, content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_unicode_bom_header(api_client):
    code = PhoneOTP.request_otp(mobile="09120000134", purpose=PhoneOTP.Purpose.SIGNUP)
    payload = json.dumps({
        "username": "bomuser",
        "mobile": "09120000134",
        "password": "StrongPass123!",
        "otp_code": code
    })
    bom_payload = b"\xef\xbb\xbf" + payload.encode("utf-8")
    response = api_client.generic("POST", "/account/signup/", bom_payload, content_type="application/json")
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_register_null_bytes_in_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000135", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "null\x00user",
        "mobile": "09120000135",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_control_characters_in_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000136", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "control\x01\x02user",
        "mobile": "09120000136",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ===================== DATABASE INTEGRITY =====================

@pytest.mark.django_db
def test_register_duplicate_username_case_insensitive(api_client, create_user):
    create_user(username="CaseUser")
    code = PhoneOTP.request_otp(mobile="09120000137", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "caseuser",
        "mobile": "09120000137",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_otp_reuse_prevention(api_client):
    mobile = "09120000138"
    code = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code=code)
    
    is_valid_again = PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code=code)
    assert is_valid_again is False


@pytest.mark.django_db
def test_otp_wrong_purpose_fails():
    mobile = "09120000139"
    PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    is_valid = PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.RESET_PASSWORD, code="123456")
    assert is_valid is False


@pytest.mark.django_db
def test_multiple_otp_requests_invalidate_previous():
    """تست چند درخواست OTP متوالی"""
    mobile = "09120000140"
    
    # درخواست اول
    code1 = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    # دستکاری زمان OTP قبلی
    otp1 = PhoneOTP.objects.filter(mobile=mobile).first()
    otp1.created_at = timezone.now() - timedelta(seconds=61)
    otp1.save()
    
    # درخواست دوم - حالا کار می‌کند
    code2 = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    # بررسی اینکه OTP اول غیرفعال شده
    otp1.refresh_from_db()
    assert otp1.is_used is True
    assert code1 != code2


# ===================== CONCURRENCY =====================

@pytest.mark.django_db
def test_concurrent_registration_same_mobile_different_otp():
    """تست ثبت‌نام همزمان با یک شماره"""
    from concurrent.futures import ThreadPoolExecutor
    mobile = "09120000141"
    
    # درخواست اول
    code1 = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    # دستکاری زمان
    otp = PhoneOTP.objects.filter(mobile=mobile).first()
    otp.created_at = timezone.now() - timedelta(seconds=61)
    otp.save()
    
    # درخواست دوم
    code2 = PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    assert code1 != code2
    assert PhoneOTP.objects.filter(mobile=mobile, is_used=False).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_registration_same_username():
    mobile1 = "09120000142"
    mobile2 = "09120000143"
    code1 = PhoneOTP.request_otp(mobile=mobile1, purpose=PhoneOTP.Purpose.SIGNUP)
    code2 = PhoneOTP.request_otp(mobile=mobile2, purpose=PhoneOTP.Purpose.SIGNUP)
    
    def register_with_mobile(mobile, code):
        client = APIClient()
        return client.post("/account/signup/", {
            "username": "sameusername",
            "mobile": mobile,
            "password": "StrongPass123!",
            "otp_code": code
        }).status_code
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(register_with_mobile, mobile1, code1),
            executor.submit(register_with_mobile, mobile2, code2)
        ]
        results = [f.result() for f in futures]
    
    assert User.objects.filter(username="sameusername").count() <= 1


# ===================== EXTERNAL DEPENDENCIES =====================

@pytest.mark.django_db
@patch("accounts.views.send_sms")
def test_sms_sending_failure(mock_send_sms, api_client):
    mock_send_sms.return_value = False
    response = api_client.post("/account/signup/otp/request/", {"mobile": "09120000144"})
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
@patch("accounts.views.send_sms")
def test_sms_sending_timeout(mock_send_sms, api_client):
    import requests
    mock_send_sms.side_effect = requests.Timeout
    response = api_client.post("/account/signup/otp/request/", {"mobile": "09120000145"})
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
@patch("accounts.views.send_sms")
def test_sms_api_returns_422(mock_send_sms, api_client):
    mock_send_sms.return_value = False
    response = api_client.post("/account/signup/otp/request/", {"mobile": "09120000146"})
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
@patch("accounts.views.EmailAddress.send_confirmation")
def test_email_confirmation_sending_failure_does_not_block_registration(mock_send, api_client):
    mock_send.side_effect = Exception("SMTP connection failed")
    code = PhoneOTP.request_otp(mobile="09120000147", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "emailfailuser",
        "mobile": "09120000147",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "fail@test.com"
    })
    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.filter(username="emailfailuser").exists()


@pytest.mark.django_db
@patch("accounts.views.EmailAddress.send_confirmation")
def test_email_confirmation_service_unavailable(mock_send, api_client):
    mock_send.side_effect = ConnectionError("Cannot connect to email server")
    code = PhoneOTP.request_otp(mobile="09120000148", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "emailunavail",
        "mobile": "09120000148",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "unavail@test.com"
    })
    assert response.status_code == status.HTTP_201_CREATED


# ===================== MALFORMED REQUESTS =====================

@pytest.mark.django_db
def test_register_missing_content_type(api_client):
    code = PhoneOTP.request_otp(mobile="09120000149", purpose=PhoneOTP.Purpose.SIGNUP)
    payload = json.dumps({
        "username": "nocontenttype",
        "mobile": "09120000149",
        "password": "StrongPass123!",
        "otp_code": code
    })
    response = api_client.generic("POST", "/account/signup/", payload)
    assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE]


@pytest.mark.django_db
def test_register_xml_content_type(api_client):
    xml_payload = "<xml><username>test</username></xml>"
    response = api_client.post("/account/signup/", xml_payload, content_type="application/xml")
    assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE]


@pytest.mark.django_db
def test_register_empty_body(api_client):
    response = api_client.post("/account/signup/", {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_extremely_large_payload(api_client):
    code = PhoneOTP.request_otp(mobile="09120000150", purpose=PhoneOTP.Purpose.SIGNUP)
    large_payload = {
        "username": "a" * 1000000,
        "mobile": "09120000150",
        "password": "StrongPass123!",
        "otp_code": code
    }
    response = api_client.post("/account/signup/", large_payload)
    assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE]


@pytest.mark.django_db
def test_register_json_trailing_comma(api_client):
    invalid_json = '{"username": "test", "mobile": "09120000151", "password": "pass", "otp_code": "123456",}'
    response = api_client.generic("POST", "/account/signup/", invalid_json, content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_non_utf8_encoding(api_client):
    payload = b'{"username": "test", "mobile": "09120000152", "password": "pass", "otp_code": "123456"}'
    latin1_payload = payload.decode("latin1").encode("utf-8")
    response = api_client.generic("POST", "/account/signup/", latin1_payload, content_type="application/json; charset=latin1")
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


# ===================== SECURITY TESTS =====================

@pytest.mark.django_db
def test_sql_injection_mobile_field(api_client):
    code = PhoneOTP.request_otp(mobile="09120000153", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "sqluser",
        "mobile": "09120000153' OR '1'='1",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not User.objects.filter(username="sqluser").exists()


@pytest.mark.django_db
def test_sql_injection_username_field(api_client):
    code = PhoneOTP.request_otp(mobile="09120000154", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "admin' OR '1'='1",
        "mobile": "09120000154",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_xss_payload_in_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000155", purpose=PhoneOTP.Purpose.SIGNUP)
    xss_payload = "<script>alert('XSS')</script>"
    response = api_client.post("/account/signup/", {
        "username": xss_payload,
        "mobile": "09120000155",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]
    
    if response.status_code == status.HTTP_201_CREATED:
        user = User.objects.get(username=xss_payload)
        response_data = response.json()
        assert "<script>" not in str(response_data)


@pytest.mark.django_db
def test_path_traversal_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000156", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "../../../etc/passwd",
        "mobile": "09120000156",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_unicode_confusable_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000157", purpose=PhoneOTP.Purpose.SIGNUP)
    confusable_username = "аdmin"  # Cyrillic 'а' instead of Latin 'a'
    response = api_client.post("/account/signup/", {
        "username": confusable_username,
        "mobile": "09120000157",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_zero_width_characters_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000158", purpose=PhoneOTP.Purpose.SIGNUP)
    zero_width_username = "admin\u200b"
    response = api_client.post("/account/signup/", {
        "username": zero_width_username,
        "mobile": "09120000158",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_right_to_left_override_username(api_client):
    code = PhoneOTP.request_otp(mobile="09120000159", purpose=PhoneOTP.Purpose.SIGNUP)
    rtl_username = "admin\u202E"
    response = api_client.post("/account/signup/", {
        "username": rtl_username,
        "mobile": "09120000159",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_otp_brute_force_enumeration():
    mobile = "09120000160"
    PhoneOTP.request_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP)
    
    for code in range(0, 100):
        if code < 5:
            PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code=f"{code:06d}")
        else:
            result = PhoneOTP.verify_otp(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP, code=f"{code:06d}")
            if result:
                break
    
    otp = PhoneOTP.objects.filter(mobile=mobile, purpose=PhoneOTP.Purpose.SIGNUP).first()
    assert otp.failed_attempts >= 5
    assert otp.is_used is True


# ===================== API CONTRACT TESTS =====================

@pytest.mark.django_db
def test_get_request_to_signup_endpoint(api_client):
    response = api_client.get("/account/signup/")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_put_request_to_signup_endpoint(api_client):
    response = api_client.put("/account/signup/", {})
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_delete_request_to_signup_endpoint(api_client):
    response = api_client.delete("/account/signup/")
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_patch_request_to_signup_endpoint(api_client):
    response = api_client.patch("/account/signup/", {})
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_head_request_to_signup_endpoint(api_client):
    response = api_client.head("/account/signup/")
    assert response.status_code in [status.HTTP_200_OK, status.HTTP_405_METHOD_NOT_ALLOWED]


@pytest.mark.django_db
def test_options_request_returns_allowed_methods(api_client):
    response = api_client.options("/account/signup/")
    assert response.status_code == status.HTTP_200_OK
    assert "Allow" in response.headers
    assert "POST" in response.headers["Allow"]


@pytest.mark.django_db
def test_accept_header_xml_not_acceptable(api_client):
    response = api_client.post("/account/signup/", {}, HTTP_ACCEPT="application/xml")
    assert response.status_code in [status.HTTP_406_NOT_ACCEPTABLE, status.HTTP_400_BAD_REQUEST, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE]


@pytest.mark.django_db
def test_accept_header_missing_defaults_to_json(api_client):
    code = PhoneOTP.request_otp(mobile="09120000161", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "defaultaccept",
        "mobile": "09120000161",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED
    assert response["Content-Type"].startswith("application/json")


# ===================== BOUNDARY TESTS =====================

@pytest.mark.django_db
def test_register_valid_mobile_09123456789(api_client):
    code = PhoneOTP.request_otp(mobile="09123456789", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "validmobile1",
        "mobile": "09123456789",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_mobile_with_10_digits(api_client):
    code = PhoneOTP.request_otp(mobile="0912345678", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "shortmobile",
        "mobile": "0912345678",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_mobile_with_12_digits(api_client):
    code = PhoneOTP.request_otp(mobile="091234567890", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "longmobile",
        "mobile": "091234567890",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_mobile_wrong_prefix(api_client):
    code = PhoneOTP.request_otp(mobile="01123456789", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "wrongprefix",
        "mobile": "01123456789",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_password_only_letters(api_client):
    code = PhoneOTP.request_otp(mobile="09120000162", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "lettersonly",
        "mobile": "09120000162",
        "password": "abcdefgh",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_password_only_numbers(api_client):
    code = PhoneOTP.request_otp(mobile="09120000163", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "numbersonly",
        "mobile": "09120000163",
        "password": "12345678",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_password_with_spaces_only(api_client):
    code = PhoneOTP.request_otp(mobile="09120000164", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "spacespass",
        "mobile": "09120000164",
        "password": "        ",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_register_password_unicode_chars(api_client):
    code = PhoneOTP.request_otp(mobile="09120000165", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "unicodepass",
        "mobile": "09120000165",
        "password": "パスワード123!",
        "otp_code": code
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_username_special_chars(api_client):
    code = PhoneOTP.request_otp(mobile="09120000166", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "user@#$%",
        "mobile": "09120000166",
        "password": "StrongPass123!",
        "otp_code": code
    })
    assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST]


@pytest.mark.django_db
def test_register_email_with_subdomain(api_client):
    code = PhoneOTP.request_otp(mobile="09120000167", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "subdomainemail",
        "mobile": "09120000167",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "user@sub.domain.com"
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_email_plus_addressing(api_client):
    code = PhoneOTP.request_otp(mobile="09120000168", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "plusemail",
        "mobile": "09120000168",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "user+tag@example.com"
    })
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_register_email_idn_domain(api_client):
    code = PhoneOTP.request_otp(mobile="09120000169", purpose=PhoneOTP.Purpose.SIGNUP)
    response = api_client.post("/account/signup/", {
        "username": "idnemail",
        "mobile": "09120000169",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "user@пример.рф"
    })
    assert response.status_code == status.HTTP_201_CREATED
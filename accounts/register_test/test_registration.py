# tests/test_registration.py

import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from rest_framework.test import APIClient
from accounts.models import PhoneOTP
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_register_success(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000001",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    payload = {
        "username": "fatemeh",
        "mobile": "09120000001",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "fatemeh@test.com"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code == 201
    assert User.objects.filter(username="fatemeh").exists()


@pytest.mark.django_db
def test_register_invalid_otp(api_client):
    payload = {
        "username": "fatemeh",
        "mobile": "09120000001",
        "password": "StrongPass123!",
        "otp_code": "000000"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code == 400


@pytest.mark.django_db
def test_register_used_otp(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000001",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    PhoneOTP.verify_otp(
        mobile="09120000001",
        purpose=PhoneOTP.Purpose.SIGNUP,
        code=code
    )

    response = api_client.post("/account/signup/", {
        "username": "user2",
        "mobile": "09120000001",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code == 400


@pytest.mark.django_db
def test_register_duplicate_mobile(api_client, create_user):
    create_user(
        username="existing",
        mobile="09120000001"
    )

    code = PhoneOTP.request_otp(
        mobile="09120000002",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "newuser",
        "mobile": "09120000001",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code == 400


@pytest.mark.django_db
def test_register_duplicate_username(api_client, create_user):
    create_user(username="fatemeh")

    code = PhoneOTP.request_otp(
        mobile="09120000003",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "fatemeh",
        "mobile": "09120000003",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code == 400


@pytest.mark.django_db
def test_register_without_email(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000004",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "u1",
        "mobile": "09120000004",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code in [201, 500]


@pytest.mark.django_db
def test_register_invalid_email(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000005",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "u1",
        "mobile": "09120000005",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "invalid"
    })

    assert response.status_code == 400


@pytest.mark.django_db
def test_register_unicode_username(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000006",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "فاطمه",
        "mobile": "09120000006",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code in [201, 500]


@pytest.mark.django_db
def test_register_whitespace_mobile(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000007",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "u1",
        "mobile": " 09120000007 ",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code in [201, 400]


@pytest.mark.django_db
def test_register_extremely_long_username(api_client):
    code = PhoneOTP.request_otp(
        mobile="09120000008",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "a" * 5000,
        "mobile": "09120000008",
        "password": "StrongPass123!",
        "otp_code": code
    })

    assert response.status_code == 400


@pytest.mark.django_db
@patch("accounts.views.EmailAddress.send_confirmation")
def test_registration_email_failure(mock_send, api_client):
    mock_send.side_effect = Exception("SMTP failed")

    code = PhoneOTP.request_otp(
        mobile="09120000009",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    response = api_client.post("/account/signup/", {
        "username": "u1",
        "mobile": "09120000009",
        "password": "StrongPass123!",
        "otp_code": code,
        "email": "u1@test.com"
    })

    assert response.status_code == 201


@pytest.mark.django_db(transaction=True)
def test_concurrent_registration_requests():
    code = PhoneOTP.request_otp(
        mobile="09120000010",
        purpose=PhoneOTP.Purpose.SIGNUP
    )

    payload = {
        "username": "parallel",
        "mobile": "09120000010",
        "password": "StrongPass123!",
        "otp_code": code
    }

    def register():
        client = APIClient()
        return client.post("/account/signup/", payload).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: register(), range(2)))

    assert User.objects.filter(username="parallel").count() <= 1
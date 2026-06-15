# tests/test_security.py

import pytest


@pytest.mark.django_db
def test_sql_injection_registration(api_client):
    payload = {
        "username": "' OR 1=1 --",
        "mobile": "09120000001",
        "password": "StrongPass123!",
        "otp_code": "000000"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code in [400, 401]


@pytest.mark.django_db
def test_xss_payload_registration(api_client):
    payload = {
        "username": "<script>alert(1)</script>",
        "mobile": "09120000002",
        "password": "StrongPass123!",
        "otp_code": "000000"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code in [400, 401]


@pytest.mark.django_db
def test_zero_width_username(api_client):
    payload = {
        "username": "admin\u200b",
        "mobile": "09120000003",
        "password": "StrongPass123!",
        "otp_code": "000000"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code in [400, 401]


@pytest.mark.django_db
def test_unicode_homoglyph_username(api_client):
    payload = {
        "username": "аdmin",
        "mobile": "09120000004",
        "password": "StrongPass123!",
        "otp_code": "000000"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code in [400, 401]


@pytest.mark.django_db
def test_extremely_large_json_body(api_client):
    payload = {
        "username": "a" * 100000,
        "mobile": "09120000005",
        "password": "StrongPass123!",
        "otp_code": "000000"
    }

    response = api_client.post("/account/signup/", payload)

    assert response.status_code in [400, 413]


@pytest.mark.django_db
def test_invalid_utf8_body(api_client):
    response = api_client.generic(
        "POST",
        "/account/signup/",
        b"\x80abc",
        content_type="application/json"
    )

    assert response.status_code in [400, 415]
# tests/test_api_contract.py

import pytest


@pytest.mark.django_db
def test_invalid_json(api_client):
    response = api_client.generic(
        "POST",
        "/account/signup/",
        b'{"invalid_json"',
        content_type="application/json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_wrong_content_type(api_client):
    response = api_client.post(
        "/account/signup/",
        "plain text",
        content_type="text/plain"
    )

    assert response.status_code in [400, 415]


@pytest.mark.django_db
def test_empty_body(api_client):
    response = api_client.post(
        "/account/signup/",
        {},
        format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_unexpected_fields(api_client):
    response = api_client.post("/account/signup/", {
        "username": "u1",
        "mobile": "09120000001",
        "password": "StrongPass123!",
        "otp_code": "000000",
        "unexpected": "field"
    })

    assert response.status_code in [400, 401]


@pytest.mark.django_db
def test_options_request(api_client):
    response = api_client.options("/account/signup/")

    assert response.status_code == 200
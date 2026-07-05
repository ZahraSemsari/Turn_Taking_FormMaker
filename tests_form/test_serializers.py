from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from Form.models import AllResponse, FieldResponse
from FormAPI.serializers import FieldSerializer, SubmitSerializer, validate_value_for_field


pytestmark = pytest.mark.django_db


def field_stub(field_type, config=None):
    return SimpleNamespace(field_type=field_type, config=config or {})


@pytest.mark.parametrize(
    "field_type, config, value",
    [
        ("text", {"min_length": 2, "max_length": 5}, "abcd"),
        ("password", {"min_length": 3}, "secret"),
        ("tag", {"regex": r"^[a-z0-9-]+$"}, "tag-1"),
        ("email", {}, "person@example.com"),
        ("phone", {}, "09123456789"),
        ("url", {}, "https://example.com/path"),
        ("number", {"min": 1, "max": 10}, 5),
        ("slider", {"min": 1, "max": 10}, 5),
        ("checkbox", {"choices": ["a", {"value": "b"}]}, ["a", "b"]),
        ("dropdown", {"choices": ["a", "b"]}, "a"),
        ("radio", {"choices": [{"value": "yes"}, {"value": "no"}]}, "yes"),
        ("switch", {"choices": [True, False]}, True),
        ("date", {}, "2026-07-04"),
        ("time", {}, "13:45:30"),
        ("file", {}, None),
    ],
)
def test_validate_value_for_field_accepts_valid_values(field_type, config, value):
    validate_value_for_field(field_stub(field_type, config), value)


@pytest.mark.parametrize(
    "field_type, config, value",
    [
        ("text", {}, 123),
        ("text", {"min_length": 3}, "ab"),
        ("text", {"max_length": 3}, "abcd"),
        ("text", {"regex": r"^[A-Z]+$"}, "abc"),
        ("email", {}, "not-an-email"),
        ("phone", {}, "123"),
        ("phone", {"regex": r"^09\d{9}$"}, "08123456789"),
        ("url", {}, "example.com"),
        ("number", {}, "10"),
        ("number", {"min": 5}, 4),
        ("slider", {"max": 5}, 6),
        ("checkbox", {"choices": ["a"]}, "a"),
        ("checkbox", {"choices": ["a"]}, ["b"]),
        ("dropdown", {"choices": ["a"]}, "b"),
        ("radio", {"choices": [{"value": "yes"}]}, "no"),
        ("date", {}, "04-07-2026"),
        ("time", {}, "25:99"),
    ],
)
def test_validate_value_for_field_rejects_invalid_values(field_type, config, value):
    with pytest.raises(serializers.ValidationError):
        validate_value_for_field(field_stub(field_type, config), value)


@pytest.mark.parametrize(
    "field_type, config, value",
    [
        ("checkbox", {"choices": "not-list"}, ["a"]),
        ("dropdown", {"choices": [{"label": "A"}]}, "a"),
    ],
)
def test_validate_value_for_field_rejects_malformed_choices_config(field_type, config, value):
    with pytest.raises(serializers.ValidationError):
        validate_value_for_field(field_stub(field_type, config), value)


def test_field_serializer_fills_default_config_when_empty_config_is_sent():
    serializer = FieldSerializer(
        data={
            "field_type": "slider",
            "config": {},
            "name": "score",
            "label": "Score",
            "order_index": 1,
            "is_required": True,
            "description": "",
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["config"] == {"min": 0, "max": 100, "step": 1}


def test_field_serializer_rejects_invalid_config():
    serializer = FieldSerializer(
        data={
            "field_type": "slider",
            "config": {"min": 10, "max": 1},
            "name": "score",
            "label": "Score",
            "order_index": 1,
            "is_required": True,
            "description": "",
        }
    )

    assert not serializer.is_valid()
    assert "config" in serializer.errors


def make_request_with_files(files=None):
    factory = APIRequestFactory()
    return factory.post("/submit/", data=files or {}, format="multipart")


def test_submit_serializer_requires_context(form, field_factory):
    field = field_factory(form=form, is_required=True)
    serializer = SubmitSerializer(
        data={"field_responses": [{"response_fields": field.id, "value": "ok"}]},
        context={},
    )

    assert not serializer.is_valid()
    assert "form" in serializer.errors


def test_submit_serializer_creates_response_and_field_values(form, field_factory):
    text_field = field_factory(
        form=form,
        field_type="text",
        name="full_name",
        config={"min_length": 2, "max_length": 30},
        is_required=True,
    )
    number_field = field_factory(
        form=form,
        field_type="number",
        name="age",
        config={"min": 18, "max": 99},
        is_required=True,
    )
    checkbox_field = field_factory(
        form=form,
        field_type="checkbox",
        name="skills",
        config={"choices": ["python", "django"]},
    )

    serializer = SubmitSerializer(
        data={
            "field_responses": [
                {"response_fields": text_field.id, "value": "Ali"},
                {"response_fields": number_field.id, "value": 25},
                {"response_fields": checkbox_field.id, "value": ["python", "django"]},
            ]
        },
        context={"form_id": form.id, "request": make_request_with_files()},
    )

    assert serializer.is_valid(), serializer.errors
    response = serializer.save()

    assert isinstance(response, AllResponse)
    assert response.form_id == form.id
    values = {
        item.response_fields_id: item.value
        for item in FieldResponse.objects.filter(response=response)
    }
    assert values == {
        text_field.id: "Ali",
        number_field.id: 25,
        checkbox_field.id: ["python", "django"],
    }


def test_submit_serializer_rejects_missing_required_field(form, field_factory):
    required_field = field_factory(form=form, is_required=True)

    serializer = SubmitSerializer(
        data={"field_responses": []},
        context={"form_id": form.id, "request": make_request_with_files()},
    )

    assert not serializer.is_valid()
    assert str(required_field.id) in str(serializer.errors["required_fields"])


def test_submit_serializer_rejects_duplicate_field_response(form, field_factory):
    field = field_factory(form=form)

    serializer = SubmitSerializer(
        data={
            "field_responses": [
                {"response_fields": field.id, "value": "first"},
                {"response_fields": field.id, "value": "second"},
            ]
        },
        context={"form_id": form.id, "request": make_request_with_files()},
    )

    assert not serializer.is_valid()
    assert "Duplicate answer" in str(serializer.errors)


def test_submit_serializer_rejects_field_from_another_form(form, form_factory, field_factory):
    other_form = form_factory()
    foreign_field = field_factory(form=other_form)

    serializer = SubmitSerializer(
        data={"field_responses": [{"response_fields": foreign_field.id, "value": "bad"}]},
        context={"form_id": form.id, "request": make_request_with_files()},
    )

    assert not serializer.is_valid()
    assert "does not belong to this form" in str(serializer.errors)


def test_submit_serializer_rejects_invalid_value(form, field_factory):
    email_field = field_factory(form=form, field_type="email", name="email", is_required=True)

    serializer = SubmitSerializer(
        data={"field_responses": [{"response_fields": email_field.id, "value": "bad-email"}]},
        context={"form_id": form.id, "request": make_request_with_files()},
    )

    assert not serializer.is_valid()
    assert "field_responses" in serializer.errors


def test_submit_serializer_file_upload_success(form, field_factory):
    file_field = field_factory(
        form=form,
        field_type="file",
        name="avatar",
        config={
            "allowed_mime_types": ["image/png"],
            "allowed_extensions": [".png"],
            "max_size_mb": 1,
        },
        is_required=True,
    )
    upload = SimpleUploadedFile("avatar.png", b"fake-png", content_type="image/png")
    request = make_request_with_files({f"file_{file_field.id}": upload})

    serializer = SubmitSerializer(
        data={"field_responses": [{"response_fields": file_field.id, "value": None}]},
        context={"form_id": form.id, "request": request},
    )

    assert serializer.is_valid(), serializer.errors
    response = serializer.save()
    field_response = response.field_responses.get(response_fields=file_field)
    assert field_response.value is None
    assert field_response.uploaded_file.name.endswith(".png")


@pytest.mark.parametrize(
    "filename, content_type, config, expected",
    [
        (
            "avatar.jpg",
            "image/png",
            {
                "allowed_mime_types": ["image/png"],
                "allowed_extensions": [".png"],
                "max_size_mb": 1,
            },
            "Invalid file extension",
        ),
        (
            "avatar.png",
            "image/jpeg",
            {
                "allowed_mime_types": ["image/png"],
                "allowed_extensions": [".png"],
                "max_size_mb": 1,
            },
            "Invalid content type",
        ),
        (
            "avatar.png",
            "image/png",
            {
                "allowed_mime_types": ["image/png"],
                "allowed_extensions": [".png"],
                "max_size_mb": 0.000001,
            },
            "File too large",
        ),
    ],
)
def test_submit_serializer_rejects_invalid_file_uploads(
    form, field_factory, filename, content_type, config, expected
):
    file_field = field_factory(
        form=form,
        field_type="file",
        name="attachment",
        config=config,
        is_required=True,
    )
    upload = SimpleUploadedFile(filename, b"fake-file-content", content_type=content_type)
    request = make_request_with_files({f"file_{file_field.id}": upload})

    serializer = SubmitSerializer(
        data={"field_responses": [{"response_fields": file_field.id, "value": None}]},
        context={"form_id": form.id, "request": request},
    )

    assert not serializer.is_valid()
    assert expected in str(serializer.errors)


def test_submit_serializer_required_file_missing(form, field_factory):
    file_field = field_factory(form=form, field_type="file", name="attachment", is_required=True)

    serializer = SubmitSerializer(
        data={"field_responses": [{"response_fields": file_field.id, "value": None}]},
        context={"form_id": form.id, "request": make_request_with_files()},
    )

    assert not serializer.is_valid()
    assert "This file is required" in str(serializer.errors)

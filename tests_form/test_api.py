import json
from io import BytesIO

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from Form.models import AllResponse, FieldResponse, FieldModel, FormModel
from Form.utils import encode_form_token


pytestmark = pytest.mark.django_db


def form_detail_url(form):
    return f"/api/forms/{form.id}/"


def fields_url(form):
    return f"/api/forms/{form.id}/fields/"


def field_detail_url(form, field):
    return f"/api/forms/{form.id}/fields/{field.id}/"


def submit_url(form):
    return f"/api/forms/{form.id}/submit/"


def responses_url(form):
    return f"/api/forms/{form.id}/responses/"


def response_detail_url(form, response):
    return f"/api/forms/{form.id}/responses/{response.id}/"


def field_responses_url(form, field):
    return f"/api/forms/{form.id}/fields/{field.id}/responses/"


def export_url(form):
    return f"/api/forms/{form.id}/export/"


def test_protected_form_list_requires_authentication(api_client):
    response = api_client.get("/api/forms/")

    assert response.status_code in {401, 403}


def test_authenticated_user_can_create_and_list_only_own_forms(
    authed_client, user, other_user, form_factory
):
    own_form = form_factory(created_by=user, title="own-form")
    form_factory(created_by=other_user, title="other-form")

    create_response = authed_client.post(
        "/api/forms/",
        {"title": "created-from-api", "description": "desc", "is_public": True},
        format="json",
    )
    assert create_response.status_code == 201, create_response.data
    assert create_response.data["title"] == "created-from-api"
    assert create_response.data["share_link"].startswith("/f/")

    list_response = authed_client.get("/api/forms/")
    assert list_response.status_code == 200
    returned_ids = {item["id"] for item in list_response.data}
    assert own_form.id in returned_ids
    assert FormModel.objects.get(title="created-from-api").id in returned_ids
    assert not FormModel.objects.filter(id__in=returned_ids, created_by=other_user).exists()


def test_user_cannot_read_update_or_delete_another_users_form(
    other_authed_client, form
):
    get_response = other_authed_client.get(form_detail_url(form))
    patch_response = other_authed_client.patch(
        form_detail_url(form), {"title": "hacked"}, format="json"
    )
    delete_response = other_authed_client.delete(form_detail_url(form))

    assert get_response.status_code == 404
    assert patch_response.status_code == 404
    assert delete_response.status_code == 404
    form.refresh_from_db()
    assert form.title != "hacked"


def test_owner_can_get_patch_nested_fields_and_delete_form(authed_client, form, field_factory):
    keep_field = field_factory(
        form=form,
        field_type="text",
        name="full_name",
        label="Full name",
        config={"min_length": 1, "max_length": 50},
    )
    deleted_field = field_factory(form=form, field_type="email", name="email", label="Email")

    patch_response = authed_client.patch(
        form_detail_url(form),
        {
            "title": "renamed-form",
            "fields": [
                {
                    "id": keep_field.id,
                    "field_type": "text",
                    "config": {"min_length": 2, "max_length": 30},
                    "name": "full_name",
                    "label": "Updated full name",
                    "order_index": 5,
                    "is_required": True,
                    "description": "updated",
                },
                {
                    "field_type": "dropdown",
                    "config": {"choices": ["a", "b"]},
                    "name": "category",
                    "label": "Category",
                    "order_index": 6,
                    "is_required": False,
                    "description": "new",
                },
            ],
        },
        format="json",
    )

    assert patch_response.status_code == 200, patch_response.data
    form.refresh_from_db()
    keep_field.refresh_from_db()
    assert form.title == "renamed-form"
    assert keep_field.label == "Updated full name"
    assert keep_field.is_required is True
    assert not FieldModel.objects.filter(id=deleted_field.id).exists()
    assert form.fields.filter(name="category", field_type="dropdown").exists()

    get_response = authed_client.get(form_detail_url(form))
    assert get_response.status_code == 200
    assert len(get_response.data["fields"]) == 2

    delete_response = authed_client.delete(form_detail_url(form))
    assert delete_response.status_code == 204
    assert not FormModel.objects.filter(id=form.id).exists()


def test_field_collection_create_list_and_bulk_patch(authed_client, form, field_factory):
    create_response = authed_client.post(
        fields_url(form),
        [
            {
                "field_type": "text",
                "config": {},
                "name": "full_name",
                "label": "Full name",
                "order_index": 1,
                "is_required": True,
                "description": "",
            },
            {
                "field_type": "slider",
                "config": {},
                "name": "score",
                "label": "Score",
                "order_index": 2,
                "is_required": False,
                "description": "",
            },
        ],
        format="json",
    )
    assert create_response.status_code == 201, create_response.data
    assert len(create_response.data) == 2
    assert FieldModel.objects.filter(form=form).count() == 2

    list_response = authed_client.get(fields_url(form))
    assert list_response.status_code == 200
    assert len(list_response.data) == 2

    existing = form.fields.get(name="full_name")
    patch_response = authed_client.patch(
        fields_url(form),
        [
            {"id": existing.id, "label": "Updated name"},
            {
                "field_type": "radio",
                "config": {"choices": ["yes", "no"]},
                "name": "confirm",
                "label": "Confirm",
                "order_index": 3,
                "is_required": True,
                "description": "",
            },
        ],
        format="json",
    )
    assert patch_response.status_code == 200, patch_response.data
    existing.refresh_from_db()
    assert existing.label == "Updated name"
    assert form.fields.filter(name="confirm").exists()


def test_field_bulk_patch_rejects_non_list_payload(authed_client, form):
    response = authed_client.patch(fields_url(form), {"name": "bad"}, format="json")

    assert response.status_code == 400
    assert response.data == {"detail": "fields must be a list"}


def test_field_detail_get_patch_delete_and_ownership(authed_client, other_authed_client, form, field_factory):
    field = field_factory(form=form, label="Old")

    other_get = other_authed_client.get(field_detail_url(form, field))
    assert other_get.status_code == 404

    get_response = authed_client.get(field_detail_url(form, field))
    assert get_response.status_code == 200
    assert get_response.data["id"] == field.id

    patch_response = authed_client.patch(
        field_detail_url(form, field), {"label": "New"}, format="json"
    )
    assert patch_response.status_code == 200, patch_response.data
    field.refresh_from_db()
    assert field.label == "New"

    delete_response = authed_client.delete(field_detail_url(form, field))
    assert delete_response.status_code == 204
    assert not FieldModel.objects.filter(id=field.id).exists()


def test_public_form_link_accepts_valid_token_and_rejects_invalid_or_private_forms(
    api_client, form, private_form
):
    token = form.share_link.strip("/").split("/", 1)[1]
    valid_response = api_client.get(f"/f/{token}/")
    assert valid_response.status_code == 200
    assert valid_response.data["id"] == form.id

    invalid_response = api_client.get("/f/not-a-valid-token/")
    assert invalid_response.status_code == 404

    private_token = encode_form_token(private_form.created_by_id, private_form.id)
    private_response = api_client.get(f"/f/{private_token}/")
    assert private_response.status_code == 404


def test_submit_api_accepts_public_form_without_authentication(api_client, form, field_factory):
    field = field_factory(
        form=form,
        field_type="text",
        name="full_name",
        config={"min_length": 2, "max_length": 30},
        is_required=True,
    )

    response = api_client.post(
        submit_url(form),
        {"field_responses": [{"response_fields": field.id, "value": "Ali"}]},
        format="json",
    )

    assert response.status_code == 201, response.data
    created_response = AllResponse.objects.get(id=response.data["response_id"])
    assert created_response.field_responses.get(response_fields=field).value == "Ali"


def test_submit_api_rejects_private_form(api_client, private_form, field_factory):
    field = field_factory(form=private_form, is_required=True)

    response = api_client.post(
        submit_url(private_form),
        {"field_responses": [{"response_fields": field.id, "value": "Ali"}]},
        format="json",
    )

    assert response.status_code == 404


def test_submit_api_rejects_invalid_json_string(api_client, form):
    response = api_client.post(
        submit_url(form),
        {"field_responses": "{not-valid-json"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data == {"field_responses": ["Invalid JSON format."]}


def test_submit_api_rejects_missing_required_value(api_client, form, field_factory):
    required_field = field_factory(form=form, is_required=True)

    response = api_client.post(submit_url(form), {"field_responses": []}, format="json")

    assert response.status_code == 400
    assert str(required_field.id) in str(response.data)


def test_submit_api_accepts_multipart_file_payload(api_client, form, field_factory):
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

    response = api_client.post(
        submit_url(form),
        {
            "field_responses": json.dumps(
                [{"response_fields": file_field.id, "value": None}]
            ),
            f"file_{file_field.id}": upload,
        },
        format="multipart",
    )

    assert response.status_code == 201, response.data
    created_response = AllResponse.objects.get(id=response.data["response_id"])
    field_response = created_response.field_responses.get(response_fields=file_field)
    assert field_response.uploaded_file.name.endswith(".png")
    assert field_response.value is None


def test_response_endpoints_return_counts_details_and_field_responses(
    authed_client, other_authed_client, form, field_factory
):
    field = field_factory(form=form, label="Full name")
    response_obj = AllResponse.objects.create(form=form)
    field_response = FieldResponse.objects.create(
        response=response_obj, response_fields=field, value="Ali"
    )

    other_list_response = other_authed_client.get(responses_url(form))
    assert other_list_response.status_code == 404

    list_response = authed_client.get(responses_url(form))
    assert list_response.status_code == 200
    assert list_response.data["answer_count"] == 1
    assert list_response.data["results"][0]["id"] == response_obj.id

    detail_response = authed_client.get(response_detail_url(form, response_obj))
    assert detail_response.status_code == 200
    assert detail_response.data["id"] == response_obj.id
    assert detail_response.data["field_responses"][0]["value"] == "Ali"

    field_responses_response = authed_client.get(field_responses_url(form, field))
    assert field_responses_response.status_code == 200
    assert field_responses_response.data[0]["id"] == field_response.id
    assert field_responses_response.data[0]["value"] == "Ali"


def test_export_responses_excel_contains_headers_and_values(
    authed_client, other_authed_client, form, field_factory
):
    name_field = field_factory(form=form, label="Name", order_index=1)
    skills_field = field_factory(
        form=form,
        field_type="checkbox",
        name="skills",
        label="Skills",
        config={"choices": ["python", "django"]},
        order_index=2,
    )
    response_obj = AllResponse.objects.create(form=form)
    FieldResponse.objects.create(response=response_obj, response_fields=name_field, value="Ali")
    FieldResponse.objects.create(
        response=response_obj,
        response_fields=skills_field,
        value=["python", "django"],
    )

    other_response = other_authed_client.get(export_url(form))
    assert other_response.status_code == 404

    response = authed_client.get(export_url(form))
    assert response.status_code == 200
    assert response["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert f'filename="form_{form.id}_responses.xlsx"' in response["Content-Disposition"]

    workbook = openpyxl.load_workbook(BytesIO(response.content))
    worksheet = workbook.active
    rows = list(worksheet.iter_rows(values_only=True))

    assert rows[0] == ("response_id", "submitted_at", "Name", "Skills")
    assert rows[1][0] == response_obj.id
    assert rows[1][2:] == ("Ali", "python, django")

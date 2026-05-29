from rest_framework import serializers
from Form.models import *
from django.db import transaction
import re
import os
from datetime import date, time
from Form.config_schema import default_config_for, validate_config_for_field
from django.core.exceptions import ValidationError as DjangoValidationError


class FormListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormModel
        fields = [
            "id",
            "title",
            "slug",
            "created_at",
            "share_link"
        ]
        read_only_fields = fields


class FormCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormModel
        fields = [
            "title",
            "description",
            "is_public",
        ]


    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            validated_data["created_by"] = user
        else:
            # اگر فرم بدون لاگین ساخته نمی‌شود، می‌تونی error بدهی
            raise serializers.ValidationError("Authentication required to create a form.")
        return super().create(validated_data)
#
# class FieldSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = FieldModel
#         fields = [
#             "id",
#             "name",
#             "field_type",
#             "config",
#         ]
#         read_only_fields = ("id",)


class FieldSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = FieldModel
        fields = [
            "id",
            "field_type",
            "config",
            "name",
            "label",
            "order_index",
            "is_required",
            "description",
        ]
        read_only_fields = [
            "form",
        ]


    def validate(self, attrs):
        field_type = attrs.get("field_type") or getattr(self.instance, "field_type", None)
        config = attrs.get("config", getattr(self.instance, "config", None))

        if field_type is None:
            return attrs

        if not config:
            config = default_config_for(field_type)
            attrs["config"] = config

        try:
            validate_config_for_field(field_type, config)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"config": exc.messages})

        return attrs


class FormDetailSerializer(serializers.ModelSerializer):
    fields = FieldSerializer(many=True)

    class Meta:
        model = FormModel
        fields = [
            "id",
            "title",
            "description",
            "is_public",
            "share_link",
            "slug",
            "created_at",
            "updated_at",
            "fields",
        ]
        read_only_fields = [
            "id",
            "share_link",
            "slug",
            "created_at",
            "updated_at",
        ]

    @transaction.atomic
    def update(self, instance, validated_data):
        fields_were_sent = "fields" in validated_data
        fields_data = validated_data.pop("fields", None) 

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if not fields_were_sent:
            return instance

        fields_data = fields_data or []

        existing_fields = {f.id: f for f in instance.fields.all()}
        kept_ids = set()

        for field_data in fields_data:
            field_id = field_data.get("id")

            if field_id and field_id in existing_fields:
                field_obj = existing_fields[field_id]

                field_data.pop("id", None)

                for attr, value in field_data.items():
                    setattr(field_obj, attr, value)
                field_obj.save()
                kept_ids.add(field_id)
            else:
                field_data.pop("id", None)
                new_field = FieldModel.objects.create(form=instance, **field_data)
                kept_ids.add(new_field.id)

        to_delete_ids = set(existing_fields.keys()) - kept_ids
        if to_delete_ids:
            FieldModel.objects.filter(form=instance, id__in=to_delete_ids).delete()

        return instance


class ResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllResponse
        fields = [
            "id" ,
            "submitted_at",
        ]
        read_only_fields = fields


#
# class ResponseDetailSerializer(serializers.ModelSerializer):
#
class ResponseFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldResponse
        fields = [
            "id",
            "value"
        ]


class ResponseDetailSerializer(serializers.ModelSerializer):
    field_responses  = ResponseFieldSerializer(many=True, read_only=True)
    class Meta:
        model = AllResponse
        fields = [
            "id" ,
            "submitted_at",
            "form",
            #"submitted_by",
            "field_responses",
        ]
        read_only_fields = fields


class FieldResponseSerializer(serializers.ModelSerializer):
    
    response_fields = serializers.PrimaryKeyRelatedField(queryset=FieldModel.objects.select_related("form"))

    class Meta:
        model = FieldResponse
        fields = [
            "id",
            "value",
            "response_fields"
        ]
        read_only_fields = ('id',)

    





class SubmitSerializer(serializers.ModelSerializer):
    field_responses = FieldResponseSerializer(many=True)

    class Meta:
        model = AllResponse
        fields = [
            "id",
            "form",
            "submitted_at",
            "field_responses",
        ]
        read_only_fields = ("id", "submitted_at")
        extra_kwargs = {"form": {"required": False}}

    def validate(self, attrs):
        form_id = self.context.get("form_id")
        if not form_id:
            raise serializers.ValidationError({"form": "Form id is required in serializer context."})
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError({"detail": "Request is required in serializer context."})

        try:
            form = FormModel.objects.prefetch_related("fields").get(pk=form_id)
        except FormModel.DoesNotExist:
            raise serializers.ValidationError({"form": "Form not found."})

        responses = attrs.get("field_responses", [])
        form_fields = {field.id: field for field in form.fields.all()}
        sent_field_ids = set()
        item_errors = {}

        for index, item in enumerate(responses):
            if not isinstance(item, dict):
                item_errors[index] = {
                    "non_field_errors": "Each item in field_responses must be an object."
                }
                continue

            field_obj = item.get("response_fields")
            value = item.get("value")

            if not field_obj:
                item_errors[index] = {"response_fields": "This field is required."}
                continue

            field_id = field_obj.id
            form_field = form_fields.get(field_id)
            
            if not form_field:
                item_errors[index] = {"response_fields": f"Field {field_id} does not belong to this form."}
                continue

            if field_id in sent_field_ids:
                item_errors[index] = {"response_fields": f"Duplicate answer for field {field_id}."}
                continue

            if form_field.field_type == "file":
                uploaded = request.FILES.get(f"file_{field_id}")

                if not uploaded:
                    if form_field.is_required:
                        item_errors[index] = {"file": "This file is required."}
                    else:
                        item_errors[index] = {"file": f"Upload file with key: file_{field_id}"}
                    continue

                config = form_field.config or {}
                allowed_mime_types = config.get("allowed_mime_types") or []
                allowed_extensions = [ext.lower() for ext in (config.get("allowed_extensions") or [])]
                max_size_mb = config.get("max_size_mb")

                if allowed_mime_types and uploaded.content_type not in allowed_mime_types:
                    item_errors[index] = {"file": f"Invalid content type: {uploaded.content_type}"}
                    continue

                file_ext = os.path.splitext(uploaded.name)[1].lower()
                if allowed_extensions and file_ext not in allowed_extensions:
                    item_errors[index] = {"file": f"Invalid file extension: {file_ext}"}
                    continue

                if max_size_mb is not None and uploaded.size > int(max_size_mb * 1024 * 1024):
                    item_errors[index] = {"file": f"File too large. Maximum size is {max_size_mb} MB."}
                    continue

                sent_field_ids.add(field_id)
                continue

            if form_field.is_required and value in (None, "", []):
                item_errors[index] = {"value": "This field is required."}
                continue

            try:
                validate_value_for_field(form_field, value)
            except serializers.ValidationError as exc:
                item_errors[index] = {"value": exc.detail}
                continue

            sent_field_ids.add(field_id)

        missing_required = [
            field.id
            for field in form_fields.values()
            if field.is_required and field.id not in sent_field_ids
        ]

        if item_errors or missing_required:
            error_payload = {}
            if item_errors:
                error_payload["field_responses"] = item_errors
            if missing_required:
                error_payload["required_fields"] = (
                    f"Missing required answers for field ids: {missing_required}"
                )
            raise serializers.ValidationError(error_payload)

        attrs["form"] = form
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        field_responses_data = validated_data.pop("field_responses", [])
        form = validated_data.pop("form")
        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError({"detail": "Request is required in serializer context."})

        response = AllResponse.objects.create(form=form)
        for item in field_responses_data:
            field_obj = item["response_fields"]
            field_response = FieldResponse(
                response=response,
                response_fields=field_obj,
            )

            if field_obj.field_type == "file":
                field_response.uploaded_file = request.FILES.get(f"file_{field_obj.id}")
                field_response.value = None
            else:
                field_response.value = item.get("value")

            field_response.save()

        return response


def validate_value_for_field(field: FieldModel, value):
    field_type = field.field_type
    config = field.config or {}

    if value in (None, "", []):
        return

    if field_type in {"text", "password", "tag"}:
        if not isinstance(value, str):
            raise serializers.ValidationError("Value must be a string.")
        _validate_string_constraints(value, config)
        return

    if field_type == "email":
        if not isinstance(value, str):
            raise serializers.ValidationError("Email must be a string.")
        serializers.EmailField().run_validation(value)
        _validate_string_constraints(value, config)
        return

    if field_type == "phone":
        if not isinstance(value, str):
            raise serializers.ValidationError("Phone must be a string.")
        pattern = config.get("regex") or r"^\d{11}$"
        if not re.fullmatch(pattern, value):
            raise serializers.ValidationError("Phone format is invalid.")
        return

    if field_type == "url":
        if not isinstance(value, str):
            raise serializers.ValidationError("URL must be a string.")
        serializers.URLField().run_validation(value)
        return

    if field_type in {"number", "slider"}:
        if not isinstance(value, (int, float)):
            raise serializers.ValidationError("Value must be a number.")
        _validate_number_constraints(value, config)
        return

    if field_type == "checkbox":
        if not isinstance(value, list):
            raise serializers.ValidationError("Checkbox value must be a list.")
        allowed_choices = _get_allowed_choices(config)
        if allowed_choices is not None:
            invalid = [item for item in value if item not in allowed_choices]
            if invalid:
                raise serializers.ValidationError(f"Invalid choices: {invalid}")
        return

    if field_type in {"dropdown", "radio", "switch"}:
        allowed_choices = _get_allowed_choices(config)
        if allowed_choices is not None and value not in allowed_choices:
            raise serializers.ValidationError(f"Value must be one of: {allowed_choices}")
        return

    if field_type == "date":
        if not isinstance(value, str):
            raise serializers.ValidationError("Date value must be a string in ISO format.")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise serializers.ValidationError("Date must be in ISO format (YYYY-MM-DD).")
        return

    if field_type == "time":
        if not isinstance(value, str):
            raise serializers.ValidationError("Time value must be a string in ISO format.")
        try:
            time.fromisoformat(value)
        except ValueError:
            raise serializers.ValidationError("Time must be in ISO format (HH:MM[:SS]).")
        return

    if field_type == "file":
        # File validation is handled in SubmitSerializer.validate() via request.FILES.
        return


def _validate_string_constraints(value, config):
    min_length = config.get("min_length")
    max_length = config.get("max_length")
    regex = config.get("regex")

    if min_length is not None and len(value) < min_length:
        raise serializers.ValidationError(f"Minimum length is {min_length}.")
    if max_length is not None and len(value) > max_length:
        raise serializers.ValidationError(f"Maximum length is {max_length}.")
    if regex and not re.fullmatch(regex, value):
        raise serializers.ValidationError("Value format is invalid.")


def _validate_number_constraints(value, config):
    min_value = config.get("min")
    max_value = config.get("max")

    if min_value is not None and value < min_value:
        raise serializers.ValidationError(f"Minimum value is {min_value}.")
    if max_value is not None and value > max_value:
        raise serializers.ValidationError(f"Maximum value is {max_value}.")


def _get_allowed_choices(config):
    choices = config.get("choices")
    if choices is None:
        return None
    if not isinstance(choices, list):
        raise serializers.ValidationError("Field config 'choices' must be a list.")

    normalized = []
    for choice in choices:
        if isinstance(choice, dict):
            if "value" in choice:
                normalized.append(choice["value"])
            else:
                raise serializers.ValidationError(
                    "Each choice object must include a 'value' key."
                )
        else:
            normalized.append(choice)
    return normalized

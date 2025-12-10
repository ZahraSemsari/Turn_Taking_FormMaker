from rest_framework import serializers
from Form.models import *


class FormListSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormModel
        fields = [
            "id",
            "title",
            "slug",
            "created_at",
        ]
        read_only_fields = fields


class FormCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormModel
        fields = [
            "title",
            "description",
            "is_public"
        ]


class FieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldModel
        fields = [
            "id",
            "name",
            "field_type",
            "config",
        ]


class FormDetailSerializer(serializers.ModelSerializer):
    fields = FieldSerializer(many=True, read_only=True)

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


class FieldDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldModel
        fields = [
            "id",
            "form",
            "field_type",
            "config",
            "name",
            "label",
            "is_required",
            "description",
        ]


class FieldCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldModel
        fields = [
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




class ResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllResponse
        fields = [
            "id" ,
            "submitted_at",
        ]
        readonly_fields = fields
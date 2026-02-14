from rest_framework import serializers
from Form.models import *
from django.db import transaction



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
        fields_data = validated_data.pop("fields", [])

        # 🔹 1. update خود فرم
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # 🔹 2. Fieldهای موجود
        existing_fields = {
            field.id: field for field in instance.fields.all()
        }

        sent_field_ids = []

        for field_data in fields_data:
            field_id = field_data.get("id")

            if field_id and field_id in existing_fields:
                # update
                field_obj = existing_fields[field_id]
                for attr, value in field_data.items():
                    setattr(field_obj, attr, value)
                field_obj.save()
                sent_field_ids.append(field_id)

            else:
                # create
                new_field = FieldModel.objects.create(
                    form=instance,
                    **field_data
                )
                sent_field_ids.append(new_field.id)

        return instance



class ResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllResponse
        fields = [
            "id" ,
            "submitted_at",
        ]
        readonly_fields = fields


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
        readonly_fields = fields


class FieldResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = FieldResponse
        fields = [
            "id",
            "value",
            "response_fields"
        ]
        read_only_fields = ('id',)

        def validate_value(self, attrs):

            for attr, value in attrs.items():
                field_id = attr.get("response_fields")
                field_type = FieldModel.objects.get(id=field_id).field_type

                if field_type == "text":
                    ...





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




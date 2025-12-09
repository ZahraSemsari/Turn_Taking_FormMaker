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

    def create(self, validated_data):
        return FormModel.objects.create(**validated_data)


    def update(self, instance, validated_data):
        instance.title = validated_data.get('title', instance.title)
        instance.description = validated_data.get('description', instance.description)
        instance.is_public = validated_data.get('is_public', instance.is_public)
        instance.save()
        return instance




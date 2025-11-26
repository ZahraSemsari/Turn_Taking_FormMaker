from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "mobile", "first_name", "last_name"]


class EmailOrUsernameOrMobileTokenObtainPairSerializer(TokenObtainPairSerializer):

    identifier = serializers.CharField(required=False)

    def validate(self, attrs):

        identifier = (
            attrs.get("identifier")
            or attrs.get("username")
            or attrs.get("email")
            or attrs.get("mobile")
        )
        password = attrs.get("password")

        if not identifier or not password:
            raise serializers.ValidationError(
                "identifier/email/username/mobile و password باید ست شوند."
            )


        identifier = str(identifier).strip()
        username_value = identifier

        try:

            if "@" in identifier:
                user = User.objects.get(email__iexact=identifier)


            elif identifier.isdigit() and len(identifier) == 11:
                user = User.objects.get(mobile=identifier)


            else:
                user = User.objects.get(username__iexact=identifier)

            username_value = user.username

        except User.DoesNotExist:
            pass


        attrs["username"] = username_value
        data = super().validate(attrs)

        data["user"] = UserSerializer(self.user).data
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["email"] = user.email
        token["mobile"] = user.mobile
        return token


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "mobile", "password")

    def validate_mobile(self, value):
        if not value.isdigit() or len(value) != 11:
            raise serializers.ValidationError("Mobile must be 11 digit.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            mobile=validated_data["mobile"],
            password=validated_data["password"],
        )
        return user


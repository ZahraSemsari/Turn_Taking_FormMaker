from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]

class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    identifier = serializers.CharField(required=False)

    def validate(self, attrs):
        identifier = attrs.get("identifier") or attrs.get("username") or attrs.get("email")
        password = attrs.get("password")
        if not identifier or not password:
            raise serializers.ValidationError("identifier/email/username and password must be set")

        username_value = identifier
        try:
            if "@" in identifier:
                user = User.objects.get(email__iexact=identifier)
                username_value = user.username
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
        return token
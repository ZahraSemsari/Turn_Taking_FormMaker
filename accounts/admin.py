# from django.contrib import admin

# from django.contrib import admin
# from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
# from .models import User

# @admin.register(User)
# class UserAdmin(BaseUserAdmin):
#     model = User
#     list_display = ("id","email","mobile","is_staff","is_active")
#     ordering = ("username",)
#     search_fields = ("username", "email",)
#     fieldsets = (
#         (None, {"fields": ("username", "email", "mobile", "password")}),
#         ("Permissions", {"fields": ("is_active","is_staff","is_superuser","groups","user_permissions")}),
#         ("Important dates", {"fields": ("last_login","date_joined")}),
#     )
#     add_fieldsets = (
#         (None,
#          {"classes": ("wide",),
#           "fields": ("email","password1","password2","is_staff","is_active")
#           }),
#     )




from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PhoneOTP, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    @admin.display(boolean=True, description="Profile completed")
    def profile_completed(self, obj):
        return bool(
            obj.username
            and obj.mobile
            and obj.has_usable_password()
        )

    @admin.display(boolean=True, description="Password set")
    def password_set(self, obj):
        return obj.has_usable_password()

    list_display = (
        "id",
        "username",
        "email",
        "mobile",
        # "is_profile_completed",
        # "has_set_password",
        "is_staff",
        "is_active",
        "date_joined",
        "profile_completed",
        "password_set",
    )
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        # "is_profile_completed",
        # "has_set_password",
        "date_joined",

    )
    search_fields = ("username", "email", "mobile", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email", "mobile")}),
        # ("Profile status", {"fields": ("is_profile_completed", "has_set_password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "mobile", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "mobile",
        "purpose",
        "is_used",
        "failed_attempts",
        "created_at",
        "expires_at",
        "locked_until",
    )
    list_filter = ("purpose", "is_used", "created_at", "expires_at")
    search_fields = ("mobile",)
    ordering = ("-created_at",)
    readonly_fields = ("code_hash", "created_at", "expires_at", "locked_until", "failed_attempts")


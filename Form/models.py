# from django.contrib.auth.models import User
from importlib.metadata import requires
from .config_schema import default_config_for, validate_config_for_field
from django.core.exceptions import ValidationError
from django.db import models
from django.forms.fields import ChoiceField
from django.urls import reverse
from django.utils.text import slugify
from django.db import models
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.signing import Signer
from .utils import encode_form_token



class FormModel(models.Model):
    """
    Represents a form created by a user.

    Each form can contain multiple fields and multiple submitted responses.
    A secure share_link is generated after creation so public users can submit it.
    """

    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, default="نام فرم")
    description = models.TextField(blank=True, null=True)
    # after creating the user
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="forms",
    )
    # created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=True)
    share_link = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'فرم'
        verbose_name_plural = 'فرم ها'

    def str(self):
        return self.title
    def get_absolute_url(self):
        """
        Return the internal detail URL for this form.
        """
        return reverse('Form:detail', args=[self.id])

    def save(self, *args, **kwargs):
        """
        Save the form and generate its secure share link when needed.

        Why two saves are used:
        - The form must first be saved to get an id.
        - Then user_id and form_id are signed into a public token.
        - Finally share_link is updated with /f/<token>/.
        """
        if not self.slug:
            self.slug = slugify(self.title , allow_unicode=True)

        
        # باید بدون share_link اول ذخیره شود تا id داشته باشد
        is_new = self.pk is None


        super().save(*args, **kwargs)

        # اگر فرم تازه ساخته شده و share_link خالی است:
        if is_new and not self.share_link:
            if not self.created_by_id:
                # اگر هنوز سیستم کاربری‌تون آماده نشده
                # می‌تونی بعدا یک migration بزنی و این قسمت رو تغییر بدی
                raise ValueError("created_by must be set before saving FormModel to generate share_link")

            from .utils import encode_form_token
            token = encode_form_token(self.created_by_id, self.id)
            # اینجا فقط path را ذخیره می‌کنیم، یا اگر دوست داشتی full URL
            self.share_link = f"/f/{token}/"

            # دوباره ذخیره، این بار فقط share_link عوض شده
            super().save(update_fields=["share_link"])


class FieldModel(models.Model):
    """
    Represents a single field inside a form.

    field_type defines the kind of input.
    config stores field-specific validation options such as choices,
    min/max values, regex, file limits, and default values.
    """
    field_name = [
        ('text' , 'متن'),
        ('number' , 'عدد'),
        ('email' , 'ایمیل'),
        ('phone' , 'موبایل'),
        ('date' , 'تاریخ'),
        ('time' , 'زمان'),
        ('checkbox' , 'چند انتخابی'),
        ('dropdown' , 'لیست کشویی'),
        ('file' , 'فایل'),
        ('radio', 'انتخابی'),
        ('switch', 'دو گزینه ای'),
        ('slider', 'اسلایدر'),
        ('password' , 'رمز'),
        ('url', 'لینک'),
        ('tag', 'تگ'),
    ]


    form = models.ForeignKey('FormModel', on_delete=models.CASCADE, related_name='fields')
    field_type = models.CharField(choices=field_name, max_length=20)
    config = models.JSONField(default=dict,blank=True) # this feature should come from the front
    name = models.CharField(max_length=200 )
    label = models.CharField(max_length=200)
    order_index = models.IntegerField(default=0)
    is_required = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)

    class Meta:
        # A field name must be unique only inside the same form.
        # Different forms may use the same field name.
        unique_together = ('form', 'name')
    
    def clean(self):
        """
        Validate field config before saving.

        If config is empty, default config is applied based on field_type.
        Then config keys and required values are validated by config_schema.
        """
        super().clean()
        if not self.config:
            self.config = default_config_for(self.field_type)
        validate_config_for_field(self.field_type, self.config)

    def save(self, *args, **kwargs):
        """
        Run full model validation before saving the field.

        This guarantees config validation is applied even when fields
        are created directly through ORM or admin.
        """
        self.full_clean()
        return super().save(*args, **kwargs)


class AllResponse(models.Model):
    """
    Represents one submitted response for a form.

    The actual answers are stored in related FieldResponse records.
    """
    form = models.ForeignKey(
        'FormModel',
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='فرم مربوطه'
    )

    # submitted_by = models.CharField(
    #     max_length=255,
    #     blank=True,
    #     null=True,
    # )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'پاسخ'
        verbose_name_plural = 'پاسخ‌ها'



class FieldResponse(models.Model):
    """
    Represents one answer for one field inside a submitted form response.

    Regular answers are stored in value as JSON.
    File answers are stored in uploaded_file.
    """
    response = models.ForeignKey(
        'AllResponse',
        on_delete=models.CASCADE,
        related_name='field_responses',
        verbose_name='پاسخ مربوطه'
    )

    response_fields = models.ForeignKey(
        'FieldModel',
        on_delete=models.CASCADE,
        related_name='response_fields',
    )

    value = models.JSONField(
        blank=True,
        null=True,
    )
    uploaded_file = models.FileField(upload_to="form_uploads/%Y/%m/%d/", null=True, blank=True)


    class Meta:
        verbose_name = 'پاسخ فیلد'
        verbose_name_plural = 'پاسخ فیلدها'

    def str(self):
        return f"{self.response_fields} : {self.value}"


    def clean(self):
        """
        Ensure this field answer belongs to the same form as the response.

        This prevents attaching an answer from Form A to a response of Form B.
        """
        if self.response.form.id != self.response_fields.form.id:
            raise ValidationError("this response is not related to this form ")



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

class FormModel(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, default="نام فرم")
    description = models.TextField(blank=True, null=True)
    # after creating the user
    # created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=True)
    share_link = models.CharField(max_length=120)
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
        return reverse('Form:detail', args=[self.id])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title , allow_unicode=True)

        if not self.share_link:
            self.share_link = f"/form/{self.slug}/"


        super().save(*args, **kwargs)


class FieldModel(models.Model):
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
    config = models.JSONField(default=dict) # this feature should come from the front
    name = models.CharField(max_length=200 )
    label = models.CharField(max_length=200)
    order_index = models.IntegerField(default=0)
    is_required = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('form', 'name')
    
    def clean(self):
        super().clean()
        if not self.config:
            self.config = default_config_for(self.field_type)
        validate_config_for_field(self.field_type, self.config)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class AllResponse(models.Model):

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


    def clean(self): # call this in the serializer
        if self.response.form.id != self.response_fields.form.id:
            raise ValidationError("this response is not related to this form ")



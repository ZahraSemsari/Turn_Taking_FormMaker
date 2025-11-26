# from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.db import models
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError

class FormModel(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200, default="نام فرم")
    description = models.TextField()
    # after creating the user
    # created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    is_public = models.BooleanField(default=True)
    share_link = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    slug = models.SlugField()

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'فرم'
        verbose_name_plural = 'فرم ها'

    def __str__(self):
        return self.title
    def get_absolute_url(self):
        return reverse('Form:detail', args=[self.id])

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)





class Response(models.Model):

    form = models.ForeignKey(
        'FormModel',
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='فرم مربوطه'
    )
    submitted_by = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'پاسخ'
        verbose_name_plural = 'پاسخ‌ها'



class FieldResponse(models.Model):
    response = models.ForeignKey(
        'Response',
        on_delete=models.CASCADE,
        related_name='field_responses',
        verbose_name='پاسخ مربوطه'
    )

    field_id = models.IntegerField(
    )
    field_type = models.CharField(
        max_length=50,
    )

    value = models.JSONField(
        blank=True,
        null=True,
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'پاسخ فیلد'
        verbose_name_plural = 'پاسخ فیلدها'

    def __str__(self):
        return f"{self.field_type} → {self.value}"

    def save(self, *args, **kwargs):

        if self.field_type == 'password' and isinstance(self.value, str):
            self.value = make_password(self.value)

        if self.value in [None, '', []] and not self.response.form.fields.filter(id=self.field_id).exists():
            raise ValidationError("not found ")

        super().save(*args, **kwargs)


class BaseField(models.Model):
    form = models.ForeignKey('FormModel', on_delete=models.CASCADE, related_name='fields')
    label = models.CharField(max_length=255)
    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    order_index = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField()

    class Meta:
        ordering = ['order_index']
        abstract = True


class TextField(BaseField):
    placeholder = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )



class NumberField(BaseField):
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    decimal_places = models.IntegerField(default=4)
    based_on = models.CharField(
        max_length=20,
        choices=[
            ('integer', 'عدد صحیح'),
            ('float', 'عدد اعشاری'),
        ],
        default='integer'
    )


class EmailField(BaseField):
    max_length = models.IntegerField(default=254)
    allowed_domains = models.JSONField(blank=True, null=True)

class PhoneField(BaseField):
    pattern = models.CharField(
        max_length=11,
        default=r'^09\d{9}$',
    )

class DateField(BaseField):
    date_format = models.CharField(
        max_length=10,
        choices=[
            ('gregorian', 'میلادی'),
            ('jalali', 'شمسی'),
        ],
        default='gregorian'
    )

class TimeField(BaseField):
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    step_minutes = models.PositiveIntegerField(default=1)
    time_format = models.CharField(
        max_length=10,
        choices=[
            ('24h', '۲۴ ساعته'),
            ('12h', '۱۲ ساعته'),
        ],
        default='24h',
    )

class CheckboxField(BaseField):
    options = models.JSONField(
        default=list,
    )
    min_selected = models.PositiveIntegerField(
        default=0,
    )
    max_selected = models.PositiveIntegerField(
        default=1,
    )

class DropDownField(BaseField):
    options = models.JSONField(
        default=list,
    )


class FileField(BaseField):
    allowed_types = models.JSONField(
        default=list
    )
    max_size = models.PositiveIntegerField(
        default=1,
    )
    choose_type_of_file = models.CharField(
        max_length=10,
        choices=[
            ('megabyte' , 'مگابایت'),
            ('kilobyte', 'کیلوبایت'),
        ],
        default='megabyte'

    )
    multiple = models.BooleanField(
        default=False,
    )

    def get_max_size_in_bytes(self):
        if self.choose_type_of_file == 'kilobyte':
            return self.max_size * 1024
        elif self.choose_type_of_file == 'megabyte':
            return self.max_size * 1024 * 1024
        else:
            raise ValidationError("واحد اندازه‌گیری حجم فایل نامعتبر است. باید یکی از 'kilobyte' یا 'megabyte' باشد.")

class RadioField(BaseField):
    options = models.CharField(

    )
class SwitchField(BaseField):
    default_value = models.BooleanField(
        default=False,
    )
    true_label = models.CharField(
        max_length=50,
        default="فعال",
    )
    false_label = models.CharField(
        max_length=50,
        default="غیرفعال",
    )

class SliderField(BaseField):
    default_value = models.IntegerField(
        default=0,
    )
    min_value = models.IntegerField(
        default=0,
    )
    max_value = models.IntegerField(
        default=10,
    )
    step = models.PositiveIntegerField(
        default=1,
    )

    def clean(self):
        if self.min_value >= self.max_value:
            self.min_value = self.max_value -1
        if self.step <= self.max_value -self.min_value or self.step < 0:
            self.step = 1



class PasswordField(BaseField):
    min_length = models.PositiveIntegerField(
        default=6,
    )
    max_length = models.PositiveIntegerField(
        default=128,
    )
    pattern = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    require_confirmation = models.BooleanField(
        default=False,
    )


class UrlField(BaseField):
    url = models.URLField()

    def clean(self):
        if self.url == '':
            self.url = None

class TagField(BaseField):
    ...


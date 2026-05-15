from django.urls import path
from .views import (
    FormListAPIView,
    FormDetailsAPIView,
    FieldListAPIView,
    FieldDetailsAPIView,
    ResponseListAPIView,
    ResponseDetailAPIView,
    ResponseFieldListAPIView,
    SubmitAPIView,
)

urlpatterns = [
    path("forms/", FormListAPIView.as_view(), name="form-list"),
    path("forms/<int:pk>/", FormDetailsAPIView.as_view(), name="form-detail"),

    path("forms/<int:pk_f>/fields/", FieldListAPIView.as_view(), name="field-list"),
    path("forms/<int:pk_f>/fields/<int:pk>/", FieldDetailsAPIView.as_view(), name="field-detail"),

    path("forms/<int:pk_f>/responses/", ResponseListAPIView.as_view(), name="response-list"),
    path("forms/<int:pk_f>/responses/<int:pk>/", ResponseDetailAPIView.as_view(), name="response-detail"),

    path("forms/<int:pk_f>/fields/<int:pk_field>/responses/", ResponseFieldListAPIView.as_view(), name="field-responses"),

    path("forms/<int:pk_f>/submit/", SubmitAPIView.as_view(), name="form-submit"),

]

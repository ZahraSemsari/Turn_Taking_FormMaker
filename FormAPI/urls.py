from django.urls import path
from .views import *


# Form API routes.
# Includes form CRUD, field CRUD, response listing/detail,
# public form submission, and Excel export.
urlpatterns = [
    path("forms/", FormListAPIView.as_view(), name="form-list"),
    path("forms/<int:pk>/", FormDetailsAPIView.as_view(), name="form-detail"),

    path("forms/<int:pk_f>/fields/", FieldListAPIView.as_view(), name="field-list"),
    path("forms/<int:pk_f>/fields/<int:pk>/", FieldDetailsAPIView.as_view(), name="field-detail"),

    path("forms/<int:pk_f>/responses/", ResponseListAPIView.as_view(), name="response-list"),
    path("forms/<int:pk_f>/responses/<int:pk>/", ResponseDetailAPIView.as_view(), name="response-detail"),

    path("forms/<int:pk_f>/fields/<int:pk_field>/responses/", ResponseFieldListAPIView.as_view(), name="field-responses"),

    path("forms/<int:pk_f>/submit/", SubmitAPIView.as_view(), name="form-submit"),

    path("forms/<int:pk_f>/export/", ExportResponsesExcelAPIView.as_view(), name="export-responses"),

    path(
        "f/<str:token>/",
        PublicFormAPIView.as_view(),
        name="public-form",
    ),


]




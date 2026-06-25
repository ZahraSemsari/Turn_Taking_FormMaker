import json

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.core import signing
from rest_framework.exceptions import NotFound
from Form.utils import decode_form_token
from Form.models import *
from . import serializers
#### for getting excel
from openpyxl import Workbook
from django.http import HttpResponse
from Form.models import FormModel
from rest_framework.permissions import IsAuthenticated, AllowAny

def get_owned_form_or_404(request, pk):
    return get_object_or_404(FormModel, pk=pk, created_by=request.user)

def get_owned_form_or_404(request, pk):
    return get_object_or_404(
        FormModel,
        pk=pk,
        created_by=request.user
    )




# Create your views here.
class FormListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        form_data = FormModel.objects.filter(created_by=request.user)
        serializer = serializers.FormListSerializer(form_data, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = serializers.FormCreateUpdateSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            form = serializer.save()
            output = serializers.FormDetailSerializer(form).data
            return Response(output, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PublicFormView(APIView):
    def get(self, request, token):
        try:
            data = decode_form_token(token)
        except signing.BadSignature:
            raise NotFound("Invalid link")

        user_id = data.get("u")
        form_id = data.get("f")

        form = get_object_or_404(FormModel, pk=form_id, created_by_id=user_id, is_public=True)

        serializer = serializers.FormDetailSerializer(form)
        return Response(serializer.data)
    


class FormDetailsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk):
        return get_owned_form_or_404(request, pk)

    def get(self, request, pk):
        form_data = self.get_object(request, pk)
        serializer = serializers.FormDetailSerializer(form_data)
        return Response(serializer.data)

    def delete(self, request, pk):
        form_data = self.get_object(request, pk)
        form_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk):
        form_data = self.get_object(request, pk)
        serializer = serializers.FormDetailSerializer(
            form_data,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FieldListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk_f):
        form = get_owned_form_or_404(request, pk_f)
        field_data = FieldModel.objects.filter(form=form)
        serializer = serializers.FieldSerializer(field_data, many=True)
        return Response(serializer.data)

    def post(self, request, pk_f):
        form = get_owned_form_or_404(request, pk_f)

        serializer = serializers.FieldSerializer(data=request.data, many=True)

        if serializer.is_valid():
            serializer.save(form=form)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk_f):
        form = get_owned_form_or_404(request, pk_f)

        fields_data = request.data

        if not isinstance(fields_data, list):
            return Response(
                {"detail": "fields must be a list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        existing_fields = {
            field.id: field for field in form.fields.all()
        }

        updated_ids = []

        for field_data in fields_data:
            field_id = field_data.get("id")

            if field_id and field_id in existing_fields:
                field_obj = existing_fields[field_id]
                serializer = serializers.FieldSerializer(
                    field_obj,
                    data=field_data,
                    partial=True
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                updated_ids.append(field_id)

            else:
                serializer = serializers.FieldSerializer(data=field_data)
                serializer.is_valid(raise_exception=True)
                serializer.save(form=form)
                updated_ids.append(serializer.instance.id)

        return Response({"updated_fields": updated_ids})




class FieldDetailsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk_f, pk):
        return get_object_or_404(
            FieldModel,
            form_id=pk_f,
            pk=pk,
            form__created_by=request.user
        )

    def get(self, request, pk_f, pk):
        field_data = self.get_object(request, pk_f, pk)
        serializer = serializers.FieldSerializer(field_data)
        return Response(serializer.data)

    def delete(self, request, pk_f, pk):
        field_data = self.get_object(request, pk_f, pk)
        field_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request, pk_f, pk):
        field_data = self.get_object(request, pk_f, pk)
        serializer = serializers.FieldSerializer(
            field_data,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class ResponseListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk_f):
        form = get_owned_form_or_404(request, pk_f)

        response_data = AllResponse.objects.filter(form=form)
        answers = response_data.count()

        response_serializer = serializers.ResponseSerializer(response_data, many=True)

        return Response({
            "answer_count": answers,
            "results": response_serializer.data
        })

    # def post(self, request , pk_f):
    #     data = request.data.copy()
    #     data['form'] = pk_f
    #     serializer = serializers.ResponseSerializer(data=data)
    #     if serializer.is_valid():
    #         serializer.save()


class ResponseDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, pk_f, pk):
        return get_object_or_404(
            AllResponse,
            form_id=pk_f,
            pk=pk,
            form__created_by=request.user
        )

    def get(self, request, pk_f, pk):
        response_data = self.get_object(request, pk_f, pk)
        response_serializer = serializers.ResponseDetailSerializer(response_data)
        return Response(response_serializer.data)



class ResponseFieldListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk_f, pk_field):
        form = get_owned_form_or_404(request, pk_f)

        responses = FieldResponse.objects.filter(
            response__form=form,
            response_fields_id=pk_field
        )

        serializer = serializers.ResponseFieldSerializer(responses, many=True)
        return Response(serializer.data)


# class SubmitAPIView(APIView):
#     parser_classes = [MultiPartParser, FormParser, JSONParser]

#     def post(self, request, pk_f):

#         serializer = serializers.SubmitSerializer(
#             data=request.data,
#             context={"form_id": pk_f, "request": request}
#         )

#         if serializer.is_valid():
#             response = serializer.save()
#             return Response({"response_id": response.id}, status=201)

#         return Response(serializer.errors, status=400)



class SubmitAPIView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk_f):
        form = get_object_or_404(FormModel, pk=pk_f, is_public=True)

        data = request.data

        field_responses_raw = data.get("field_responses")

        if isinstance(field_responses_raw, str):
            try:
                parsed = json.loads(field_responses_raw)
            except json.JSONDecodeError:
                return Response(
                    {"field_responses": ["Invalid JSON format."]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            data = {"field_responses": parsed}

        serializer = serializers.SubmitSerializer(
            data=data,
            context={"form_id": form.id, "request": request}
        )

        if serializer.is_valid():
            response = serializer.save()
            return Response({"response_id": response.id}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExportResponsesExcelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk_f):
        form = get_object_or_404(
            FormModel.objects.prefetch_related(
                "fields",
                "responses__field_responses"
            ),
            pk=pk_f,
            created_by=request.user
        )

        fields = list(form.fields.all().order_by("order_index"))
        responses = form.responses.all()

        wb = Workbook()
        ws = wb.active
        ws.title = "Responses"

        headers = ["response_id", "submitted_at"] + [f.label for f in fields]
        ws.append(headers)

        for response_obj in responses:
            field_map = {
                fr.response_fields_id: fr
                for fr in response_obj.field_responses.all()
            }

            submitted = response_obj.submitted_at
            if submitted:
                submitted = submitted.replace(tzinfo=None).isoformat(sep=" ")

            row = [response_obj.id, submitted]

            for field in fields:
                fr = field_map.get(field.id)

                if not fr:
                    row.append("")
                    continue

                value = fr.value

                if field.field_type == "file":
                    value = fr.uploaded_file.url if fr.uploaded_file else ""

                elif isinstance(value, list):
                    value = ", ".join(map(str, value))

                elif hasattr(value, "isoformat"):
                    value = value.isoformat()

                elif isinstance(value, dict):
                    value = json.dumps(value)

                row.append(value)

            ws.append(row)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="form_{form.id}_responses.xlsx"'
        wb.save(response)

        return response
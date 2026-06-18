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



# Create your views here.
class FormListAPIView(APIView):
    def get(self, request):
        form_data = FormModel.objects.all()
        serializer = serializers.FormListSerializer(form_data , many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = serializers.FormCreateUpdateSerializer(
            data=request.data,
            context={"request": request}
        )
        if serializer.is_valid():
            form = serializer.save()
            # اینجا form.share_link آماده است
            from .serializers import FormDetailSerializer
            output = FormDetailSerializer(form).data
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
    def get_object(self, pk):
        try:
            return FormModel.objects.get(pk=pk)
        except FormModel.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        form_data = self.get_object(pk)
        serializer = serializers.FormDetailSerializer(form_data)
        return Response(serializer.data)

    def delete(self, request , pk):
        form_data = self.get_object(pk)
        form_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self , request , pk):
        form_data = self.get_object(pk)
        # serializer = serializers.FormCreateUpdateSerializer(form_data, data=request.data, partial=True)
        serializer = serializers.FormDetailSerializer(form_data, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class FieldListAPIView(APIView):
    def get(self, request , pk_f ):
        field_data = FieldModel.objects.filter(form_id=pk_f)
        serializer = serializers.FieldSerializer(field_data, many=True)
        return Response(serializer.data)


    def post(self, request , pk_f):
        serializer = serializers.FieldSerializer(data=request.data , many=True)
        if serializer.is_valid():
            serializer.save(form=FormModel.objects.get(pk=pk_f))
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk_f):
        fields_data = request.data

        if not isinstance(fields_data, list):
            return Response(
                {"detail": "fields must be a list"},
                status=status.HTTP_400_BAD_REQUEST
            )

        form = get_object_or_404(FormModel, pk=pk_f)

        existing_fields = {
            field.id: field for field in form.fields.all()
        }

        updated_ids = []

        for field_data in fields_data:
            field_id = field_data.get("id")

            if field_id and field_id in existing_fields:
                # update
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
                # create
                serializer = serializers.FieldSerializer(data=field_data)
                serializer.is_valid(raise_exception=True)
                serializer.save(form=form)
                updated_ids.append(serializer.instance.id)

        return Response({"updated_fields": updated_ids})

class FieldDetailsAPIView(APIView):
    def get_object(self, pk_f ,pk ):
        try:
            return FieldModel.objects.get(form_id=pk_f, pk=pk)
        except FieldModel.DoesNotExist:
            raise Http404

    def get(self, request, pk_f ,pk):
        field_data = self.get_object( pk_f ,pk)
        serializer = serializers.FieldSerializer(field_data)
        return Response(serializer.data)

    def delete(self, request , pk_f ,pk):
        field_data = self.get_object(pk_f ,pk)
        field_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self, request , pk_f ,pk):
        field_data = self.get_object(pk_f ,pk)
        serializer = serializers.FieldSerializer(field_data, data=request.data , partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResponseListAPIView(APIView):
    def get(self, request, pk_f):
        response_data = AllResponse.objects.filter(form_id=pk_f)
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
    def get_object(self , pk_f , pk):
        try :
            response_data = AllResponse.objects.get(form_id=pk_f, pk=pk)
        except AllResponse.DoesNotExist:
            raise Http404
        return response_data

    def get(self, request, pk_f, pk):
        response_data = self.get_object(pk_f, pk)

        form_id = response_data.form_id


        response_serializer = serializers.ResponseDetailSerializer(response_data)


        return Response(response_serializer.data)


    # def delete(self, request , pk_f , pk):
    #     response_data = self.get_object( pk_f , pk)
    #     response_data.delete()
    #     return Response(status=status.HTTP_204_NO_CONTENT)



class ResponseFieldListAPIView(APIView):
    def get(self, request, pk_f, pk_field):
        responses = FieldResponse.objects.filter(
            response__form_id=pk_f,
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk_f):
        data = request.data

        # اگر field_responses به صورت string (در multipart) آمده باشد، آن را JSON parse کن
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
            context={"form_id": pk_f, "request": request}
        )

        if serializer.is_valid():
            response = serializer.save()
            return Response({"response_id": response.id}, status=201)

        return Response(serializer.errors, status=400)


    #  ########### changes for getting excel

class ExportResponsesExcelAPIView(APIView):

    def get(self, request, pk_f):

        form = get_object_or_404(
            FormModel.objects.prefetch_related(
                "fields",
                "responses__field_responses"
            ),
            pk=pk_f
        )

        fields = list(form.fields.all().order_by("order_index"))
        responses = form.responses.all()

        wb = Workbook()
        ws = wb.active
        ws.title = "Responses"

        headers = ["response_id", "submitted_at"] + [f.label for f in fields]
        ws.append(headers)

        for response in responses:

            field_map = {
                fr.response_fields_id: fr
                for fr in response.field_responses.all()
            }

            submitted = response.submitted_at
            if submitted:
                submitted = submitted.replace(tzinfo=None).isoformat(sep=" ")
            row = [response.id, submitted]

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
                    import json
                    value = json.dumps(value)

                row.append(value)

            ws.append(row)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f'attachment; filename="form_{form.id}_responses.xlsx"'
        wb.save(response)

        return response
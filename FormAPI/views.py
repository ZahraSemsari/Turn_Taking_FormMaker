from django.http import Http404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from Form.models import *
from . import serializers

# Create your views here.
class FormListAPIView(APIView):
    def get(self, request):
        form_data = FormModel.objects.all()
        serializer = serializers.FormListSerializer(form_data , many=True)
        return Response(serializer.data)

    def post(self, request):
        form_data = serializers.formModelSerializer(data=request.data)
        if form_data.is_valid():
            form_data.save()
            return Response(form_data.data, status=status.HTTP_201_CREATED)
        return Response(form_data.errors, status=status.HTTP_400_BAD_REQUEST)


class FormDetailsAPIView(APIView):
    def get_object(self, pk):
        try:
            return FormModel.objects.get(pk=pk)
        except FormModel.DoesNotExist:
            raise Http404

    def get(self, request, pk):
        form_data = self.get_object(pk)
        serializer = serializers.FormSerializer(form_data)
        return Response(serializer.data)

    def delete(self, request , pk):
        form_data = self.get_object(pk)
        form_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def patch(self , request , pk):
        form_data = self.get_object(pk)
        serializer = serializers.FormSerializer(form_data, data=request.data, partial=True)
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
        data = request.data.copy()
        data['form'] = pk_f
        serializer = serializers.FieldSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    def get(self , request , pk_f):
        response_data = AllResponse.objects.filter(form_id=pk_f)

        response_serializer = serializers.ResponseSerializer(response_data, many=True)
        return Response(response_serializer.data)

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
        answers = response_data.field_responses.all()

        form_id = response_data.form_id
        total_fields = FieldModel.objects.filter(form_id=form_id).count()
        answered_fields = answers.count()

        response_serializer = serializers.ResponseSerializer(response_data)
        answers_serializer = serializers.ResponseFieldSerializer(answers, many=True)

        return Response({
            "id": response_serializer.data["id"],
            "form_id": form_id,
            "submitted_by": response_serializer.data["submitted_by"],
            "submitted_at": response_serializer.data["submitted_at"],
            "total_fields": total_fields,
            "answered_fields": answered_fields,
            "answers": answers_serializer.data
        })


    def delete(self, request , pk_f , pk):
        response_data = self.get_object( pk_f , pk)
        response_data.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    def patch(self, request , pk_f , pk):
        response_data = self.get_object( pk_f , pk)
        serializer = serializers.ResponseSerializer(response_data , data = request.data , partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResponseFieldListAPIView(APIView):
    def get(self, request, pk_response, pk_field):
        response_data = FieldResponse.objects.filter(response__form_id=pk_response, response_fields_id=pk_field)
        serializer = serializers.ResponseFieldSerializer(response_data, many=True)
        return Response(serializer.data)


class SubmitAPIView(APIView):
    def post(self, request, pk_f):

        serializer = serializers.SubmitSerializer(
            data=request.data,
            context={"form_id": pk_f}
        )

        if serializer.is_valid():
            response = serializer.save()
            return Response({"response_id": response.id}, status=201)

        return Response(serializer.errors, status=400)



from django.http import Http404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from Form.models import FormModel, FieldModel
from . import serializers

# Create your views here.
class FormListAPIView(APIView):
    def get(self, request):
        form_data = FormModel.objects.all()
        serializer = serializers.FormSerializer(form_data , many=True)
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


class ResponseAPIView(APIView):
    ...
class SubmitFormAPIView(APIView):
    ...

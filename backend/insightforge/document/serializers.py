from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'original_name', 'file_size', 'uploaded_at']


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):

        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("File size must be under 50MB.")
        return value

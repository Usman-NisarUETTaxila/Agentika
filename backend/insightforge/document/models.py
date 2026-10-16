from django.db import models
import os
import uuid

def document_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join('documents/', filename)

class Document(models.Model):
    file = models.FileField(upload_to=document_upload_path)
    original_name = models.CharField(max_length=255)
    file_size = models.IntegerField(help_text="Size in bytes")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name

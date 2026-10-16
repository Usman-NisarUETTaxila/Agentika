from django.db import models

# Create your models here.
class SearchQuery(models.Model):
    query = models.TextField()
    collection_name = models.CharField(max_length=255)
    options = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.collection_name}: {self.query[:50]}..."
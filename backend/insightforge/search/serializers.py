from rest_framework import serializers


class SearchQuerySerializer(serializers.Serializer):
    """
    Validates the incoming chat/search request body.
    Only `query` is required; `collection` defaults to "Docs".
    """
    query = serializers.CharField(required=True, allow_blank=False)
    collection = serializers.CharField(required=False, default="Docs")
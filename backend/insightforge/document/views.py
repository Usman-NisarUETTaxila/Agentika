import uuid
from rest_framework import generics, status
from rest_framework.response import Response
from .models import Document
from .serializers import DocumentSerializer, DocumentUploadSerializer

COLLECTION_NAME = "Docs"  # single shared Qdrant collection


def process_single_upload(file_path, original_name):
    """
    Parse a document and ingest every element into Qdrant.

    Each element gets a UUID so multiple documents never collide, and the
    `source` payload field is always set to original_name so per-document
    deletion works correctly.
    """
    from .doc_parser import parse_document
    from .batchingest import _upload_to_qdrant

    print(f"[InsightForge] Parsing: {original_name}")
    try:
        parsed = parse_document(file_path, doc_type="auto")
        points = []

        for element in parsed.get("elements", []):
            el_type = element.get("type")

            # Skip navigational noise
            if el_type in ("toc_entry",):
                continue

            text = element.get("text", "").strip()
            if not text:
                continue

            points.append({
                # UUID guarantees no ID collision across documents
                "id": uuid.uuid4().hex,
                "text": text,
                "source": original_name,   # used for per-doc delete
                "page": element.get("page"),
                "element_type": el_type,
                "level": element.get("level"),
            })

        print(f"[InsightForge] Uploading {len(points)} elements from '{original_name}' to Qdrant collection '{COLLECTION_NAME}'")
        _upload_to_qdrant(points, collection_name=COLLECTION_NAME)
        print(f"[InsightForge] Done: '{original_name}'")

    except Exception as e:
        import traceback
        print(f"[InsightForge] ERROR processing '{original_name}': {e}")
        traceback.print_exc()
        raise

class DocumentListCreateView(generics.ListCreateAPIView):
    queryset = Document.objects.all().order_by('-uploaded_at')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return DocumentUploadSerializer
        return DocumentSerializer

    def create(self, request, *args, **kwargs):
        if Document.objects.count() >= 5:
            return Response(
                {"error": "Maximum limit of 5 documents reached."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_obj = serializer.validated_data['file']
        
        doc = Document.objects.create(
            file=file_obj,
            original_name=file_obj.name,
            file_size=file_obj.size
        )
        
        # Trigger processing synchronously so the frontend waits until parsing is fully complete
        process_single_upload(doc.file.path, doc.original_name)
        
        output_serializer = DocumentSerializer(doc)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

class DocumentDeleteView(generics.DestroyAPIView):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer

    def perform_destroy(self, instance):
        # 1. Delete physical file from media/documents/
        if instance.file:
            import os
            if os.path.isfile(instance.file.path):
                os.remove(instance.file.path)
                
        # 2. Wipe the parsed vectors from Qdrant
        try:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue
            from .qdrant_conn import ensure_source_index, get_client

            client = get_client()  # QDRANT_URL / QDRANT_API_KEY from the environment
            # Qdrant Cloud strict mode rejects filtered deletes on unindexed fields
            ensure_source_index(client, COLLECTION_NAME)
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=instance.original_name)
                        )
                    ]
                )
            )
            print(f"Successfully wiped all vectors for {instance.original_name} from Qdrant.")
        except Exception as e:
            print(f"Error deleting vectors from Qdrant: {e}")

        # 3. Delete the record from SQLite
        instance.delete()
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import SearchQuerySerializer
from .tool import agent, resume_agent, start_agent


class ContextSelectionSerializer(serializers.Serializer):
    """Second request of the flow: the user picked one of the offered contexts."""
    thread_id = serializers.CharField()
    selection = serializers.IntegerField(min_value=1)  # 1-based option number
    collection = serializers.CharField(required=False)


class SearchQueryView(APIView):
    """
    POST /api/search/

    1) {query, collection}
         -> {answer}                                   normal reply
         -> {needs_clarification, thread_id, contexts} documents clash; ask the user
    2) {thread_id, selection, collection?}
         -> {answer}                                   answer from the chosen context
    """

    def post(self, request):
        if "thread_id" in request.data:
            return self._resume(request)
        return self._start(request)

    # ------------------------------------------------------------------ #
    def _start(self, request):
        serializer = SearchQuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        question = serializer.validated_data["query"]
        collection = serializer.validated_data["collection"]

        try:
            thread_id, result = start_agent(question, collection)
        except Exception as e:
            # tool.py raises "Vector search failed: ..." / "LLM generation failed: ..."
            return Response({"error": str(e)}, status=500)

        return self._format(thread_id, result)

    def _resume(self, request):
        serializer = ContextSelectionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        thread_id = serializer.validated_data["thread_id"]
        selection = serializer.validated_data["selection"]

        # The paused run lives in the checkpointer; if it's gone (server restart,
        # already answered, wrong id) there is nothing to resume.
        snapshot = agent.get_state({"configurable": {"thread_id": thread_id}})
        if not snapshot.next:
            return Response(
                {"error": "This context selection has expired. Please ask your question again."},
                status=410,
            )

        contexts = snapshot.values.get("contexts") or []
        if selection > len(contexts):
            return Response({"error": "Invalid context selection."}, status=400)

        try:
            result = resume_agent(thread_id, str(selection))
        except Exception as e:
            return Response({"error": str(e)}, status=500)

        return self._format(thread_id, result)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _format(thread_id, result):
        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            return Response(
                {
                    "needs_clarification": True,
                    "thread_id": thread_id,
                    "contexts": payload["options"],  # [{label, description, sources}]
                },
                status=200,
            )
        return Response({"answer": result["answer"]}, status=200)
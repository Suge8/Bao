from __future__ import annotations


class _GeminiEmbedding:
    """Thin wrapper using google-genai SDK (avoids legacy google-generativeai dependency)."""

    def __init__(self, model: str, api_key: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    def compute_source_embeddings(self, texts: list[str]) -> list[list[float]]:
        result = self._client.models.embed_content(
            model=self._model,
            contents=[str(t) for t in texts],
            config={"task_type": "RETRIEVAL_DOCUMENT"},
        )
        return [e.values or [] for e in (result.embeddings or [])]

    def compute_query_embeddings(self, query: str) -> list[list[float]]:
        result = self._client.models.embed_content(
            model=self._model,
            contents=[query],
            config={"task_type": "RETRIEVAL_QUERY"},
        )
        return [e.values or [] for e in (result.embeddings or [])]

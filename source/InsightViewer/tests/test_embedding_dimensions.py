import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ai.errors import ProviderRequestError  # noqa: E402  # type: ignore[import-not-found]
from ai.providers.openai_provider import OpenAIProvider  # noqa: E402  # type: ignore[import-not-found]
from ai.types import EmbedRequest  # noqa: E402  # type: ignore[import-not-found]


class _Response:
    ok = True

    @staticmethod
    def json():
        return {"data": [{"embedding": [0.0] * 1024}]}


class EmbeddingDimensionTests(unittest.TestCase):
    def test_openai_request_uses_requested_dimensions(self):
        provider = OpenAIProvider(api_key="test-key")
        request = EmbedRequest(
            text="some chunk",
            model="text-embedding-3-large",
            dimensions=1024,
        )
        with patch("ai.providers.openai_provider.requests.post", return_value=_Response()) as post:
            response = provider.embed(request)
        self.assertEqual(len(response.embedding), 1024)
        self.assertEqual(post.call_args.kwargs["json"]["dimensions"], 1024)

    def test_dimensions_reject_unsupported_openai_embedding_model(self):
        provider = OpenAIProvider(api_key="test-key")
        request = EmbedRequest(text="some chunk", model="text-embedding-ada-002", dimensions=1024)
        with patch("ai.providers.openai_provider.requests.post") as post:
            with self.assertRaises(ProviderRequestError):
                provider.embed(request)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from unittest.mock import patch, MagicMock
from app.rag.sparse_embed import embed_sparse


class TestEmbedSparse:
    def test_disabled_returns_empty(self):
        with patch("app.rag.sparse_embed.settings") as mock_settings:
            mock_settings.sparse_enabled = False
            result = embed_sparse(["hello", "world"])
            assert result == [{}, {}]

    def test_unsupported_provider_returns_empty(self):
        with patch("app.rag.sparse_embed.settings") as mock_settings:
            mock_settings.sparse_enabled = True
            mock_settings.sparse_provider = "unknown"
            result = embed_sparse(["hello"])
            assert result == [{}]

    def test_empty_input_returns_empty(self):
        result = embed_sparse([])
        assert result == []

    @patch("httpx.post")
    def test_successful_embedding(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"sparse": {1: 0.5, 2: 0.3}},
                {"sparse": {3: 0.8}},
            ]
        }
        mock_post.return_value = mock_response

        with patch("app.rag.sparse_embed.settings") as mock_settings:
            mock_settings.sparse_enabled = True
            mock_settings.sparse_provider = "siliconflow"
            mock_settings.siliconflow_base_url = "https://api.siliconflow.cn/v1"
            mock_settings.siliconflow_api_key = "test-key"
            mock_settings.sparse_model = "BAAI/bge-m3"

            result = embed_sparse(["hello", "world"])

            assert len(result) == 2
            assert result[0] == {1: 0.5, 2: 0.3}
            assert result[1] == {3: 0.8}

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["model"] == "BAAI/bge-m3"
            assert call_kwargs["json"]["input"] == ["hello", "world"]

    @patch("httpx.post")
    def test_empty_sparse_in_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"sparse": {}},
                {},
            ]
        }
        mock_post.return_value = mock_response

        with patch("app.rag.sparse_embed.settings") as mock_settings:
            mock_settings.sparse_enabled = True
            mock_settings.sparse_provider = "siliconflow"
            mock_settings.siliconflow_base_url = "https://api.siliconflow.cn/v1"
            mock_settings.siliconflow_api_key = "test-key"
            mock_settings.sparse_model = "BAAI/bge-m3"

            result = embed_sparse(["a", "b"])
            assert result == [{}, {}]

    @patch("httpx.post")
    def test_api_error_returns_empty(self, mock_post):
        mock_post.side_effect = Exception("API timeout")

        with patch("app.rag.sparse_embed.settings") as mock_settings:
            mock_settings.sparse_enabled = True
            mock_settings.sparse_provider = "siliconflow"
            mock_settings.siliconflow_base_url = "https://api.siliconflow.cn/v1"
            mock_settings.siliconflow_api_key = "test-key"
            mock_settings.sparse_model = "BAAI/bge-m3"

            result = embed_sparse(["hello"])
            assert result == [{}]

    @patch("httpx.post")
    def test_batching(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"data": [{"sparse": {i: 0.5}} for i in range(3)]}
        mock_post.return_value = mock_response

        with patch("app.rag.sparse_embed.settings") as mock_settings:
            mock_settings.sparse_enabled = True
            mock_settings.sparse_provider = "siliconflow"
            mock_settings.siliconflow_base_url = "https://api.siliconflow.cn/v1"
            mock_settings.siliconflow_api_key = "test-key"
            mock_settings.sparse_model = "BAAI/bge-m3"

            texts = [f"text_{i}" for i in range(3)]
            result = embed_sparse(texts)
            assert len(result) == 3

import os
import pytest
from unittest.mock import patch, MagicMock
import agents.llm_client as llm_module


@pytest.fixture(autouse=True)
def reset_singleton():
    """Isolate each test from singleton state."""
    llm_module._reset()
    yield
    llm_module._reset()


class TestGetClient:
    def test_groq_key_selects_groq(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("agents.llm_client.OpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                client, model = llm_module.get_client()
                call_kwargs = mock_openai.call_args[1]
                assert "groq.com" in call_kwargs["base_url"]
                assert "llama" in model

    def test_xai_key_takes_priority_over_groq(self):
        env = {"XAI_API_KEY": "xai_test", "GROQ_API_KEY": "gsk_test"}
        with patch.dict(os.environ, env):
            with patch("agents.llm_client.OpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                _, model = llm_module.get_client()
                call_kwargs = mock_openai.call_args[1]
                assert "x.ai" in call_kwargs["base_url"]
                assert "grok" in model

    def test_gemini_key_selects_gemini(self):
        clean_env = {"GEMINI_API_KEY": "gem_test", "XAI_API_KEY": "", "GROQ_API_KEY": ""}
        with patch.dict(os.environ, clean_env):
            os.environ.pop("XAI_API_KEY", None)
            os.environ.pop("GROQ_API_KEY", None)
            with patch("agents.llm_client.OpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                _, model = llm_module.get_client()
                call_kwargs = mock_openai.call_args[1]
                assert "google" in call_kwargs["base_url"]
                assert "gemini" in model

    def test_no_key_raises_runtime_error(self):
        env_clean = {k: "" for k in ("XAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY")}
        with patch.dict(os.environ, env_clean):
            # also remove them entirely
            for k in env_clean:
                os.environ.pop(k, None)
            with pytest.raises(RuntimeError, match="No LLM API key"):
                llm_module.get_client()

    def test_singleton_returns_same_client(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("agents.llm_client.OpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                c1, _ = llm_module.get_client()
                c2, _ = llm_module.get_client()
                assert c1 is c2
                assert mock_openai.call_count == 1  # constructed only once

    def test_reset_clears_singleton(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("agents.llm_client.OpenAI") as mock_openai:
                mock_openai.return_value = MagicMock()
                llm_module.get_client()
                llm_module._reset()
                llm_module.get_client()
                assert mock_openai.call_count == 2


class TestChat:
    def test_returns_content_string(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "hello"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("agents.llm_client.get_client", return_value=(mock_client, "test-model")):
            result = llm_module.chat([{"role": "user", "content": "hi"}])
        assert result == "hello"

    def test_none_content_returns_empty_string(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = None
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("agents.llm_client.get_client", return_value=(mock_client, "test-model")):
            result = llm_module.chat([{"role": "user", "content": "hi"}])
        assert result == ""

    def test_passes_kwargs_to_api(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ok"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("agents.llm_client.get_client", return_value=(mock_client, "default-model")):
            llm_module.chat(
                [{"role": "user", "content": "hi"}],
                temperature=0.1,
                max_tokens=100,
            )
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 100

    def test_explicit_model_overrides_default(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "ok"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("agents.llm_client.get_client", return_value=(mock_client, "default-model")):
            llm_module.chat([{"role": "user", "content": "hi"}], model="override-model")
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "override-model"

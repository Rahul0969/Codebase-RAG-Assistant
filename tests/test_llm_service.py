import io
import json
import os
import socket
import unittest
import urllib.error
from unittest.mock import patch

from backend.app import llm_service
from backend.app.llm_service import (
    LLMConfigError, OllamaModelNotFoundError, OllamaResponseError,
    OllamaTimeoutError, OllamaUnavailableError, check_ollama, generate_chat, get_settings,
)


class FakeResponse:
    def __init__(self, payload):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, result=None, error=None, results=None):
        self.result, self.error, self.requests = result, error, []
        self.results = list(results or [])

    def open(self, request, timeout=None):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        if self.results:
            return self.results.pop(0)
        return self.result


def patched(opener):
    return patch.object(llm_service, "_opener", return_value=opener)


MESSAGES = [{"role": "user", "content": "hi"}]


class TestLLMService(unittest.TestCase):
    def setUp(self):
        for name in list(os.environ):
            if name.startswith("OLLAMA_"):
                self.addCleanup(os.environ.__setitem__, name, os.environ[name])
                del os.environ[name]

    def test_successful_chat_uses_configured_model_and_options(self):
        opener = FakeOpener(results=[
            FakeResponse({"models": [{"name": "qwen2.5:3b", "details": {"parameter_size": "3B"}}]}),
            FakeResponse({"model": "qwen2.5:3b", "message": {"content": " Hello "}}),
        ])
        with patched(opener):
            result = generate_chat(MESSAGES)
        self.assertEqual(result["text"], "Hello")
        self.assertEqual(result["model"], "qwen2.5:3b")
        self.assertEqual(result["mode"], "AUTO")
        request, timeout = opener.requests[1]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "qwen2.5:3b")
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"]["num_ctx"], 4096)
        self.assertEqual(timeout, 120.0)
        self.assertTrue(request.full_url.startswith("http://localhost:11434/api/chat"))

    def test_environment_overrides(self):
        os.environ.update({"OLLAMA_MODEL": "qwen2.5:1.5b", "OLLAMA_TIMEOUT": "30",
                           "OLLAMA_BASE_URL": "http://127.0.0.1:9999/"})
        settings = get_settings()
        self.assertEqual((settings.model, settings.timeout, settings.base_url),
                         ("qwen2.5:1.5b", 30.0, "http://127.0.0.1:9999"))

    def test_remote_base_url_is_rejected(self):
        for url in ("http://example.com:11434", "http://192.168.1.5:11434", "ftp://localhost"):
            os.environ["OLLAMA_BASE_URL"] = url
            with self.assertRaises(LLMConfigError):
                get_settings()

    def test_invalid_timeout_is_rejected(self):
        os.environ["OLLAMA_TIMEOUT"] = "abc"
        with self.assertRaises(LLMConfigError):
            get_settings()

    def test_connection_refused(self):
        error = urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        with patched(FakeOpener(error=error)), self.assertRaises(OllamaUnavailableError) as ctx:
            generate_chat(MESSAGES)
        self.assertNotIn("10061", str(ctx.exception))

    def test_model_not_found_from_404(self):
        error = urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b'{"error":"model not found"}'))
        with patched(FakeOpener(error=error)), self.assertRaises(OllamaModelNotFoundError) as ctx:
            generate_chat(MESSAGES)
        self.assertIn("ollama pull qwen2.5:3b", str(ctx.exception))

    def test_timeout(self):
        for error in (socket.timeout(), urllib.error.URLError(socket.timeout())):
            with patched(FakeOpener(error=error)), self.assertRaises(OllamaTimeoutError):
                generate_chat(MESSAGES)

    def test_other_http_error_maps_to_response_error(self):
        error = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"{}"))
        with patched(FakeOpener(error=error)), self.assertRaises(OllamaResponseError):
            generate_chat(MESSAGES)

    def test_malformed_responses(self):
        for payload in (b"not json", b"[]", {"message": {}}, {"message": {"content": "  "}}, {"x": 1}):
            with patched(FakeOpener(FakeResponse(payload))), self.assertRaises(OllamaResponseError):
                generate_chat(MESSAGES)

    def test_empty_messages_rejected(self):
        with self.assertRaises(ValueError):
            generate_chat([])

    def test_check_ollama_reports_model_availability(self):
        tags = {"models": [{"name": "qwen2.5:3b"}, {"name": "llama3:latest"}]}
        with patched(FakeOpener(FakeResponse(tags))):
            status = check_ollama()
        self.assertTrue(status["model_available"])
        os.environ["OLLAMA_MODEL"] = "qwen2.5:7b"
        with patched(FakeOpener(FakeResponse(tags))):
            self.assertFalse(check_ollama()["model_available"])


if __name__ == "__main__":
    unittest.main()

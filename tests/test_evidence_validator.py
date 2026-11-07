import unittest
from unittest.mock import patch

from backend.app.evidence_validator import extract_citations, validate_answer
from backend.app.main import AskRequest, ask_repository_endpoint
from backend.app.rag_service import SYSTEM_PROMPT, ask_repository


def chunk(source_id, path, start, end, content="def f(): pass", shown_end=None):
    return {"source_id": source_id, "file_path": path, "start_line": start, "end_line": end,
            "context_start_line": start, "context_end_line": shown_end or end,
            "language": "python", "kind": "function_definition", "symbol": "f",
            "similarity": 0.8, "distance": 0.2, "content": content}


AUTH = chunk(1, "src/auth.py", 15, 32, "def authenticate_user(user):\n    return check(user)")
TOKEN = chunk(2, "src/token.py", 8, 24, "def create_access_token(data):\n    return sign(data)")


class TestExtraction(unittest.TestCase):
    def test_extracts_single_range_and_line_forms(self):
        found = extract_citations("See [src/auth.py:15-32] and [src/auth.py:20] and [src\\token.py:L8-L24].")
        self.assertEqual([c["text"] for c in found],
                         ["src/auth.py:15-32", "src/auth.py:20", "src/token.py:8-24"])

    def test_multiple_citations_in_one_bracket_and_duplicates(self):
        found = extract_citations("[src/auth.py:15-32, src/token.py:8-24] again [src/auth.py:15-32]")
        self.assertEqual(len(found), 2)

    def test_ignores_non_citation_brackets(self):
        self.assertEqual(extract_citations("Step [1], see [docs](http://x.io) and [Note: 5] or [a:b]"), [])


class TestValidation(unittest.TestCase):
    def test_valid_multiple_citations_verified(self):
        answer = ("The application validates credentials in the `authenticate_user` function [src/auth.py:15-32]. "
                  "It then creates an access token in `create_access_token` [src/token.py:8-24].")
        result = validate_answer(answer, [AUTH, TOKEN])
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["evidence_status"], "verified")
        self.assertEqual(result["evidence_coverage"]["cited_source_ids"], [1, 2])
        self.assertEqual(result["unsupported_citations"], [])

    def test_invalid_file_path(self):
        result = validate_answer("Login is in [src/login.py:1-5].", [AUTH])
        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["evidence_status"], "invalid_citations")
        self.assertEqual(result["unsupported_citations"][0]["reason"], "file_not_retrieved")

    def test_invalid_line_numbers(self):
        for text in ("[src/auth.py:0-5]", "[src/auth.py:30-20]"):
            result = validate_answer(f"It works {text}.", [AUTH])
            self.assertEqual(result["evidence_status"], "invalid_citations", text)
            self.assertEqual(result["citations"][0]["reason"], "invalid_line_range")

    def test_range_outside_retrieved_chunks(self):
        for text in ("[src/auth.py:100-120]", "[src/auth.py:10-20]", "[src/auth.py:30-40]"):
            result = validate_answer(f"It works {text}.", [AUTH])
            self.assertEqual(result["unsupported_citations"][0]["reason"], "lines_outside_retrieved_range", text)

    def test_range_spanning_adjacent_chunks_is_valid(self):
        second = chunk(2, "src/auth.py", 33, 40)
        result = validate_answer("It spans both [src/auth.py:30-38].", [AUTH, second])
        self.assertTrue(result["validation_passed"])

    def test_truncated_context_limits_valid_range(self):
        shown = chunk(1, "src/auth.py", 15, 32, shown_end=20)
        self.assertEqual(validate_answer("Ok [src/auth.py:15-20].", [shown])["evidence_status"], "verified")
        self.assertEqual(validate_answer("Ok [src/auth.py:15-30].", [shown])["evidence_status"], "invalid_citations")

    def test_mixed_valid_and_invalid_reports_invalid(self):
        result = validate_answer("A [src/auth.py:15-32] and B [src/nope.py:1-2].", [AUTH])
        self.assertEqual(result["evidence_status"], "invalid_citations")
        self.assertEqual(len(result["unsupported_citations"]), 1)
        self.assertEqual(len([c for c in result["citations"] if c["valid"]]), 1)

    def test_missing_citations(self):
        result = validate_answer("The function checks the user password carefully before login.", [AUTH])
        self.assertEqual(result["evidence_status"], "no_citations")
        self.assertFalse(result["validation_passed"])

    def test_empty_evidence_is_insufficient(self):
        result = validate_answer("Anything [src/auth.py:1-2]", [])
        self.assertEqual(result["evidence_status"], "insufficient_evidence")
        self.assertFalse(result["validation_passed"])

    def test_model_declaring_insufficient_evidence(self):
        answer = "The retrieved code does not contain enough information to answer this."
        result = validate_answer(answer, [AUTH])
        self.assertEqual(result["evidence_status"], "insufficient_evidence")
        self.assertFalse(result["validation_passed"])

    def test_uncited_claims_downgrade_to_partial(self):
        answer = ("The function validates the user [src/auth.py:15-32]. "
                  "Afterwards it writes an audit record to the database for every attempt.")
        result = validate_answer(answer, [AUTH])
        self.assertEqual(result["evidence_status"], "partially_verified")
        self.assertTrue(result["validation_passed"])
        self.assertEqual(result["evidence_coverage"]["uncited_claim_examples"],
                         ["Afterwards it writes an audit record to the database for every attempt."])

    def test_unsupported_identifier_is_flagged(self):
        answer = "It calls `hash_password()` to verify the user [src/auth.py:15-32]."
        result = validate_answer(answer, [AUTH])
        self.assertEqual(result["unsupported_identifiers"], ["hash_password()"])
        self.assertEqual(result["evidence_status"], "partially_verified")

    def test_system_prompt_requires_citation_format(self):
        self.assertIn("[path:start-end]", SYSTEM_PROMPT)
        self.assertIn("Never invent a file path or a line number", SYSTEM_PROMPT)


def search_result(matches):
    return {"repository_name": "demo", "query": "q", "result_count": len(matches),
            "embedding_model": "m", "matches": matches}


MATCH = {"chunk_id": "c1", "content": "def login(user):\n    return check(user)", "file_path": "src/auth.py",
         "language": "python", "kind": "function_definition", "symbol": "login",
         "start_line": 10, "end_line": 11, "distance": 0.2, "similarity": 0.8}


class TestEvidenceAwareRag(unittest.TestCase):
    def run_rag(self, answer, **kwargs):
        with patch("backend.app.rag_service.search_repository", return_value=search_result([dict(MATCH)])), \
             patch("backend.app.rag_service.generate_chat", return_value={"text": answer, "model": "qwen2.5:3b"}):
            return ask_repository("C:/repo", "Where is login?", **kwargs)

    def test_valid_evidence_aware_response(self):
        result = self.run_rag("`login` checks the user with check [src/auth.py:10-11].")
        self.assertEqual(result["evidence_status"], "verified")
        self.assertTrue(result["validation_passed"])
        self.assertTrue(result["success"])
        self.assertEqual(result["citations"][0]["source_id"], 1)
        self.assertTrue(result["retrieved_chunks"][0]["cited"])
        self.assertNotIn("content", result["retrieved_chunks"][0])
        self.assertIn("citation", result["evidence_summary"])

    def test_invalid_citation_is_flagged_not_hidden(self):
        result = self.run_rag("Login lives in [src/other.py:1-9].")
        self.assertEqual(result["evidence_status"], "invalid_citations")
        self.assertFalse(result["validation_passed"])
        self.assertEqual(result["unsupported_citations"][0]["text"], "src/other.py:1-9")
        self.assertIn("Login lives", result["answer"])

    def test_source_text_is_opt_in(self):
        result = self.run_rag("It checks [src/auth.py:10-11].", include_source_text=True)
        self.assertIn("def login", result["retrieved_chunks"][0]["content"])

    def test_no_retrieval_is_insufficient_without_llm(self):
        with patch("backend.app.rag_service.search_repository", return_value=search_result([])), \
             patch("backend.app.rag_service.generate_chat") as chat:
            result = ask_repository("C:/repo", "Where is login?")
        chat.assert_not_called()
        self.assertEqual(result["evidence_status"], "insufficient_evidence")
        self.assertEqual(result["citations"], [])
        self.assertFalse(result["success"])

    def test_api_response_structure(self):
        request = AskRequest(repository_path="C:/repo", question="Where is login?", include_source_text=True)
        with patch("backend.app.rag_service.search_repository", return_value=search_result([dict(MATCH)])), \
             patch("backend.app.rag_service.generate_chat",
                   return_value={"text": "It checks [src/auth.py:10-11].", "model": "qwen2.5:3b"}):
            result = ask_repository_endpoint(request)
        expected = {"answer", "citations", "evidence_status", "validation_passed", "unsupported_citations",
                    "retrieved_chunks", "evidence_summary", "sources", "model", "success", "retrieved_count"}
        self.assertTrue(expected <= set(result))


if __name__ == "__main__":
    unittest.main()

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../backend"))

from app.verifier import Verifier
from app.schemas import VerifierResultPayload

class TestVerifierLogic:
    def test_parse_json_basic(self):
        v = Verifier()
        assert v._parse_json('{"foo": "bar"}') == {"foo": "bar"}

    def test_parse_json_markdown(self):
        v = Verifier()
        txt = "```json\n{\"verdict\": \"pass\"}\n```"
        assert v._parse_json(txt) == {"verdict": "pass"}

    def test_parse_json_messy(self):
        v = Verifier()
        txt = "Here is the result: {\"verdict\": \"fail\", \"reason\": \"bad\"}."
        assert v._parse_json(txt) == {"verdict": "fail", "reason": "bad"}

    @patch("app.verifier.requests.post")
    def test_verify_mock_call(self, mock_post):
        # Mock response
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "{\"verdict\": \"pass\", \"confidence\": 0.9, \"reason\": \"ok\", \"suggested_actions\": []}"
                }
            }]
        }
        mock_post.return_value = mock_resp

        v = Verifier(api_key="test")
        res = v.verify("task", "agent1", "agent2", "msg")

        assert res.verdict == "pass"
        assert res.confidence == 0.9

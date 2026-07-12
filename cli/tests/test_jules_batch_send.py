# pylint: disable=import-outside-toplevel,missing-docstring,redefined-outer-name,reimported,unused-argument
from unittest.mock import MagicMock, patch

import pytest
from dev_tools.services.jules import JulesClient


@pytest.fixture
def jules_client():
    with patch.dict("os.environ", {"JULES_API_KEY": "fake_key"}):
        return JulesClient()


def test_send_single_message(jules_client):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_post.return_value = mock_response

        res = jules_client.send_message("session1", "hello")

        assert res["status"] == "success"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0].endswith("/sessions/session1:sendMessage")
        assert kwargs["json"] == {"prompt": "hello"}


def test_send_batch_message_success(jules_client):
    with patch("requests.post") as mock_post:
        # Mock responses arriving out of order to test reconstruction
        mock_res1 = MagicMock()
        mock_res1.status_code = 200
        mock_res1.json.return_value = {"status": "success"}

        mock_res2 = MagicMock()
        mock_res2.status_code = 200
        mock_res2.json.return_value = {"status": "success"}

        # side_effect returns results for session2 then session1
        def side_effect(url, **kwargs):
            if "session2" in url:
                return mock_res2
            return mock_res1

        mock_post.side_effect = side_effect

        session_ids = ["session1", "session2"]
        res = jules_client.send_message(session_ids, "hello batch")

        assert res["status"] == "success"
        assert "2/2 successful" in res["message"]
        assert len(res["results"]) == 2
        # Verify order is preserved: session1, then session2
        assert res["results"][0]["sessionId"] == "session1"
        assert res["results"][1]["sessionId"] == "session2"


def test_send_batch_message_partial_failure(jules_client):
    with patch("requests.post") as mock_post:

        def side_effect(url, **kwargs):
            mock_res = MagicMock()
            if "session2" in url:
                mock_res.status_code = 500
                mock_res.raise_for_status.side_effect = Exception("API Error")
                return mock_res
            mock_res.status_code = 200
            mock_res.json.return_value = {"status": "success"}
            return mock_res

        mock_post.side_effect = side_effect

        session_ids = ["session1", "session2"]
        res = jules_client.send_message(session_ids, "hello partial")

        assert res["status"] == "success"  # At least one succeeded
        assert "1/2 successful" in res["message"]

        # Check results order
        assert res["results"][0]["sessionId"] == "session1"
        assert res["results"][0]["status"] == "success"
        assert res["results"][1]["sessionId"] == "session2"
        assert res["results"][1]["status"] == "error"


def test_send_batch_hard_cap(jules_client):
    from dev_tools.models import JulesSendMessageInput
    from pydantic import ValidationError

    # Model should now raise error for > 50 IDs
    session_ids = [f"s{i}" for i in range(51)]
    with pytest.raises(ValidationError) as exc:
        JulesSendMessageInput(sessionId=session_ids, message="msg")
    assert "Batch size exceeds" in str(exc.value)


def test_validation_invalid_ids():
    import pytest
    from dev_tools.models import JulesSendMessageInput
    from pydantic import ValidationError

    # Test invalid characters
    with pytest.raises(ValidationError) as exc:
        JulesSendMessageInput(sessionId="bad;id", message="msg")
    assert "Invalid characters" in str(exc.value)

    # Test empty list
    with pytest.raises(ValidationError) as exc:
        JulesSendMessageInput(sessionId=[], message="msg")
    assert "sessionId list cannot be empty" in str(exc.value)

    # Test whitespace ID
    with pytest.raises(ValidationError) as exc:
        JulesSendMessageInput(sessionId=["  "], message="msg")
    assert "cannot be empty or whitespace" in str(exc.value)

    # Test empty message
    with pytest.raises(ValidationError) as exc:
        JulesSendMessageInput(sessionId="sid", message="  ")
    assert "Message cannot be empty" in str(exc.value)

from unittest.mock import patch, MagicMock
from jobscout.integrations.imessage import send_imessage


@patch("jobscout.integrations.imessage.subprocess.run")
def test_send_imessage(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    send_imessage("JobScout: 3 new roles — check Pigeon")
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "osascript" in cmd

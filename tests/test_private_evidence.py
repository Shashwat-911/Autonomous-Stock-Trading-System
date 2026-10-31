import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from analytics.private_evidence import upload
from research.replay import replay

class PrivateEvidenceTests(unittest.TestCase):
    def test_public_destination_refused_before_upload(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"private": false}'
        with patch.dict('os.environ',{'GIT_TOKEN':'test'}), patch('analytics.private_evidence.urllib.request.urlopen',return_value=response) as request:
            with self.assertRaises(RuntimeError): upload(Path('does-not-exist'))
            self.assertEqual(request.call_count,1)
    def test_replay_rejects_wrong_revision(self):
        with patch('research.replay.subprocess.check_output',return_value='actual'):
            self.assertEqual(replay({'revision':'other'})['status'],'BLOCKED_REVISION_MISMATCH')

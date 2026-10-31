import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.cloud import run

class CloudResearchTests(unittest.TestCase):
    def test_api_failure_records_failure_and_never_promotes(self):
        with tempfile.TemporaryDirectory() as directory, patch('research.cloud.PaperReader',side_effect=ValueError('SECRET')):
            with self.assertRaises(RuntimeError): run(directory)
            text=(Path(directory)/'status.json').read_text()
            self.assertNotIn('SECRET',text)
            self.assertEqual(json.loads(text)['status'],'FAILED')
            self.assertFalse(json.loads(text)['promotion_eligible'])

    def test_observation_is_sanitized_and_not_a_strategy_approval(self):
        with tempfile.TemporaryDirectory() as directory, patch('research.cloud.PaperReader'), patch('research.cloud.collect',return_value={'activities':[], 'orders':[], 'secret':'DO_NOT_PUBLISH'}):
            run(directory)
            text=(Path(directory)/'status.json').read_text()
            self.assertNotIn('DO_NOT_PUBLISH',text)
            self.assertFalse(json.loads(text)['promotion_eligible'])
            self.assertEqual(json.loads(text)['completed_episodes'],0)

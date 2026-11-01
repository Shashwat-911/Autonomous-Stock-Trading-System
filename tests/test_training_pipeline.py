import json,tempfile,unittest
from pathlib import Path
import pandas as pd
from ml.run_pipeline import run_training

class TrainingPipelineTests(unittest.TestCase):
    def test_training_is_independent_of_legacy_optimizer(self):
        with tempfile.TemporaryDirectory() as folder:
            status=run_training(lambda:pd.DataFrame({'feature':[1]}),lambda **kwargs:None,folder)
            self.assertEqual(status['model_status'],'TRAINED_RESEARCH_ONLY')
            self.assertFalse(status['promotion_eligible'])
            self.assertEqual(status['optimization_status'],'DISABLED_UNVALIDATED_LEGACY_SIMULATOR')
    def test_failure_preserves_status_and_propagates(self):
        def broken(**kwargs): raise ValueError('failed training')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                run_training(lambda:pd.DataFrame({'feature':[1]}),broken,folder)
            self.assertEqual(json.loads((Path(folder)/'training_status.json').read_text())['model_status'],'FAILED')

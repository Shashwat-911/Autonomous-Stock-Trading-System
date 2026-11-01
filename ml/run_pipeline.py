"""Weekly research model training. Legacy optimization is not a deployment gate."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run_training(build=None, train=None, output=None):
    if build is None:
        from ml.data_pipeline import build_dataset
        build = build_dataset
    if train is None:
        from ml.train_model import train_meta_labeling_model
        train = train_meta_labeling_model
    output = Path(output or Path(__file__).resolve().parent)
    output.mkdir(parents=True, exist_ok=True)
    status = {'model_status':'RUNNING', 'promotion_eligible':False,
              'optimization_status':'DISABLED_UNVALIDATED_LEGACY_SIMULATOR',
              'reason':'Legacy optimizer does not reproduce live execution; run separately only for research.'}
    path = output/'training_status.json'
    path.write_text(json.dumps(status,indent=2))
    try:
        data = build()
        if data.empty:
            raise ValueError('No training samples')
        training = output/'training_data.csv'
        data.to_csv(training)
        train(data_path=str(training))
        status.update(model_status='TRAINED_RESEARCH_ONLY', samples=len(data))
    except Exception as exc:
        status.update(model_status='FAILED',error_type=type(exc).__name__)
        raise
    finally:
        path.write_text(json.dumps(status,indent=2))
    print(json.dumps(status,indent=2))
    return status

if __name__ == '__main__':
    run_training()

"""Phase 4 tests: severity model training/inference, tool integration with
fallback, and the root-cause eval harness."""

import pytest

from app.config import get_settings
from app.ml.eval_agent import run_eval
from app.ml.features import SEVERITIES
from app.ml.model import SeverityModel
from app.ml.train import MODEL_FILE, generate_training_frame, train
from app.services.llm import MockLLMClient
from app.tools.base import ToolContext
from app.tools.heuristics import predict_severity


@pytest.fixture(scope="module")
def trained_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("model")
    metrics = train(rows=1500, model_dir=out, seed=7)
    return out, metrics


def test_generated_frame_is_learnable():
    df = generate_training_frame(rows=300, seed=1)
    assert set(df["severity"].unique()) <= set(SEVERITIES)
    assert df["severity"].nunique() == 4  # all classes represented
    assert df["alertname"].nunique() == 4
    assert (df["error_rate_pct"] >= 0).all()


def test_train_saves_model_and_honest_metrics(trained_dir):
    out, metrics = trained_dir
    assert (out / MODEL_FILE).exists()
    assert (out / "metrics.json").exists()

    assert 0.75 <= metrics["accuracy"] < 1.0  # noisy labels: good but not perfect
    assert metrics["f1_macro"] >= 0.65
    cm = metrics["confusion_matrix"]
    assert len(cm) == 4 and all(len(row) == 4 for row in cm)
    assert set(metrics["per_class"]) == set(SEVERITIES)
    assert all("precision" in stats and "recall" in stats for stats in metrics["per_class"].values())


def test_model_predicts_with_imputation(trained_dir):
    out, _ = trained_dir
    model = SeverityModel.load(out / MODEL_FILE)

    result = model.predict(
        {
            "alertname": "HighErrorRate",
            "error_rate_pct": 13.5,
            "latency_p95_ms": 2300,
            "deploy_within_hour": True,
        }
    )
    assert result["severity"] in ("high", "critical")  # unambiguous bad day
    assert abs(sum(result["probabilities"].values()) - 1.0) < 0.01
    assert "request_rate_rps" in result["imputed_features"]  # missing -> median
    assert result["method"].startswith("ml/")

    calm = model.predict({"alertname": "HighLatencyP95", "error_rate_pct": 0.2, "latency_p95_ms": 350})
    assert calm["severity"] in ("low", "medium")

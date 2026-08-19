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


async def test_tool_prefers_model_and_falls_back(trained_dir, session_factory, monkeypatch):
    out, _ = trained_dir
    model = SeverityModel.load(out / MODEL_FILE)

    async with session_factory() as db:
        ctx = ToolContext(db=db, settings=get_settings())

        monkeypatch.setattr("app.ml.model.get_severity_model", lambda: model)
        ml_result = await predict_severity(
            ctx, service="checkout-service", alertname="HighErrorRate", error_rate_pct=12.0
        )
        assert ml_result["method"].startswith("ml/")
        assert "probabilities" in ml_result

        monkeypatch.setattr("app.ml.model.get_severity_model", lambda: None)
        heuristic_result = await predict_severity(
            ctx, service="checkout-service", alertname="HighErrorRate", error_rate_pct=12.0,
            latency_p95_ms=2200, deploy_within_hour=True,
        )
        assert heuristic_result["method"].startswith("heuristic")
        assert heuristic_result["severity"] == "critical"


async def test_eval_ranker_hits_planted_culprits():
    report = await run_eval(use_agent=False)

    assert report["cases"] == 12
    assert report["ranker"]["top1_accuracy"] >= 0.75
    # the two designed misses keep the metric honest
    misses = [r["case"] for r in report["per_case"] if not r["ranker_correct"]]
    assert len(misses) <= 3


async def test_eval_agent_pipeline_end_to_end():
    report = await run_eval(limit=2, use_agent=True, llm=MockLLMClient())

    assert report["agent"]["total"] == 2
    for row in report["per_case"]:
        assert row["run_status"] == "completed"
        assert row["agent_top"]  # mock grounds its verdict in the ranker output
    # on these two clean cases the pipeline should attribute correctly
    assert report["agent"]["top1_accuracy"] == 1.0
    assert report["agent"]["candidate_recall"] >= report["agent"]["top1_accuracy"]

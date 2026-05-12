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


def test_generated_frame_is_learnable():
    df = generate_training_frame(rows=300, seed=1)
    assert set(df["severity"].unique()) <= set(SEVERITIES)
    assert df["severity"].nunique() == 4  # all classes represented
    assert df["alertname"].nunique() == 4
    assert (df["error_rate_pct"] >= 0).all()

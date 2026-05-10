"""Runtime severity model: loads the trained artifact once and predicts from
whatever features the agent supplies (missing numerics are imputed with
training medians and reported back)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from app.config import get_settings
from app.ml.features import NUMERIC_FEATURES
from app.ml.train import MODEL_FILE


class SeverityModel:
    def __init__(self, bundle: dict) -> None:
        self._pipeline = bundle["pipeline"]
        self.classes: list[str] = bundle["classes"]
        self.features: list[str] = bundle["features"]
        self.medians: dict[str, float] = bundle["feature_medians"]
        self.metrics: dict = bundle.get("metrics", {})

    @classmethod
    def load(cls, path: Path) -> "SeverityModel":
        return cls(joblib.load(path))

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {"alertname": features.get("alertname") or "HighErrorRate"}
        imputed: list[str] = []
        for name in NUMERIC_FEATURES:
            value = features.get(name)
            if name == "deploy_within_hour":
                value = int(bool(value)) if value is not None else None
            if value is None:
                value = self.medians[name]
                imputed.append(name)
            row[name] = float(value)

        frame = pd.DataFrame([row], columns=self.features)
        probabilities = self._pipeline.predict_proba(frame)[0]
        best = int(probabilities.argmax())

        return {
            "severity": self.classes[best],
            "probabilities": {
                cls: round(float(p), 3) for cls, p in zip(self.classes, probabilities)
            },
            "imputed_features": imputed,
            "method": "ml/hist-gradient-boosting-v1",
            "model_test_accuracy": self.metrics.get("accuracy"),
        }

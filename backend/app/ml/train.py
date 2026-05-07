"""Train the severity classifier.

    python -m app.ml.train [--rows 600] [--out DIR]

Training data is generated from seeded, alert-conditioned distributions with a
noisy latent risk score deciding the label — the same signal shape as real
incident data (the 30 curated rows in data/historical_incidents.csv are too few
to train on; they remain the agent's retrieval context). The label noise keeps
test accuracy honest (~85-90%) instead of a meaningless 100%.

Artifacts (model bundle + metrics.json with accuracy/F1/precision/recall and
the confusion matrix) are written to MODEL_DIR and loaded at runtime by
app.ml.model.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.config import get_settings
from app.ml.features import ALERTNAMES, FEATURES, NUMERIC_FEATURES, SEVERITIES

MODEL_FILE = "severity_model.joblib"
METRICS_FILE = "metrics.json"


def generate_training_frame(rows: int = 600, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    records = []
    for _ in range(rows):
        alertname = rng.choice(ALERTNAMES, p=[0.35, 0.25, 0.2, 0.2])

        error_rate = float(rng.gamma(1.5, 1.2))
        latency = float(rng.normal(420, 160))
        rps = float(abs(rng.normal(120, 45)))
        cpu = float(np.clip(rng.normal(52, 13), 5, 100))
        memory = float(np.clip(rng.normal(63, 11), 20, 100))
        deploy = bool(rng.random() < 0.35)

        if alertname == "HighErrorRate":
            error_rate += float(rng.gamma(2.0, 3.0))
        elif alertname == "HighLatencyP95":
            latency += float(abs(rng.normal(1300, 650)))
        elif alertname == "DBConnectionPoolExhausted":
            latency += float(abs(rng.normal(3200, 2100)))
            error_rate += float(rng.gamma(1.5, 1.6))
        elif alertname == "HighMemoryUsage":
            memory = float(rng.uniform(78, 97))

        error_rate = float(np.clip(error_rate, 0, 25))
        latency = float(np.clip(latency, 50, 12000))

        records.append(
            {
                "alertname": alertname,
                "error_rate_pct": round(error_rate, 2),
                "latency_p95_ms": round(latency, 1),
                "request_rate_rps": round(rps, 1),
                "cpu_pct": round(cpu, 1),
                "memory_pct": round(memory, 1),
                "deploy_within_hour": int(deploy),
            }
        )

    return pd.DataFrame.from_records(records)

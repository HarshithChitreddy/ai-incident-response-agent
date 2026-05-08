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

        # continuous latent risk score (how an SRE weighs the signals) plus a
        # little label noise — keeps the mapping learnable but imperfect, so
        # test accuracy stays honest instead of a meaningless 100%
        score = (
            0.30 * error_rate
            + 0.9 * float(np.log1p(latency / 300))
            + 0.05 * max(0.0, memory - 78)
            + 1.1 * deploy
            + 0.01 * max(0.0, cpu - 70)
            + float(rng.normal(0, 0.10))
        )

        records.append(
            {
                "alertname": alertname,
                "error_rate_pct": round(error_rate, 2),
                "latency_p95_ms": round(latency, 1),
                "request_rate_rps": round(rps, 1),
                "cpu_pct": round(cpu, 1),
                "memory_pct": round(memory, 1),
                "deploy_within_hour": int(deploy),
                "_score": score,
            }
        )

    df = pd.DataFrame.from_records(records)
    # quantile boundaries -> balanced classes: 40% low, 25% medium, 20% high, 15% critical
    df["severity"] = pd.qcut(df["_score"], q=[0, 0.40, 0.65, 0.85, 1.0], labels=SEVERITIES)
    df["severity"] = df["severity"].astype(str)
    return df.drop(columns=["_score"])


def train(rows: int = 1500, model_dir: Path | str | None = None, seed: int = 7) -> dict:
    model_dir = Path(model_dir or get_settings().model_dir)
    df = generate_training_frame(rows=rows, seed=seed)

    X, y = df[FEATURES], df["severity"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )

    pipeline = Pipeline(
        [
            (
                "prep",
                ColumnTransformer(
                    [("alert", OneHotEncoder(sparse_output=False, handle_unknown="ignore"), ["alertname"])],
                    remainder="passthrough",
                ),
            ),
            ("clf", HistGradientBoostingClassifier(max_iter=300, random_state=seed)),
        ]
    )
    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    precision, recall, f1, support = precision_recall_fscore_support(
        y_test, y_pred, labels=SEVERITIES, zero_division=0
    )
    metrics = {
        "model": "HistGradientBoostingClassifier",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "features": FEATURES,
        "labels": SEVERITIES,
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_test, y_pred, average="macro")), 4),
        "per_class": {
            label: {
                "precision": round(float(p), 4),
                "recall": round(float(r), 4),
                "f1": round(float(f), 4),
                "support": int(s),
            }
            for label, p, r, f, s in zip(SEVERITIES, precision, recall, f1, support)
        },
        "confusion_matrix": confusion_matrix(y_test, y_pred, labels=SEVERITIES).tolist(),
    }

    bundle = {
        "version": 1,
        "pipeline": pipeline,
        "classes": list(pipeline.named_steps["clf"].classes_),
        "features": FEATURES,
        "feature_medians": {f: float(X_train[f].median()) for f in NUMERIC_FEATURES},
        "metrics": metrics,
    }

    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_dir / MODEL_FILE)
    (model_dir / METRICS_FILE).write_text(json.dumps(metrics, indent=2))
    return metrics

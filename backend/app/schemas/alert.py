"""Prometheus Alertmanager v4 webhook schema.

Field names follow Alertmanager's wire format (camelCase) via aliases so real
Alertmanager payloads and the synthetic simulator both validate unchanged.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlertmanagerAlert(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["firing", "resolved"]
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(alias="startsAt")
    # Alertmanager sends year-1 zero value ("0001-01-01T00:00:00Z") while firing
    ends_at: datetime | None = Field(default=None, alias="endsAt")
    generator_url: str = Field(default="", alias="generatorURL")
    fingerprint: str = ""


class AlertmanagerWebhook(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: str = "4"
    group_key: str = Field(default="", alias="groupKey")
    status: Literal["firing", "resolved"] = "firing"
    receiver: str = ""
    group_labels: dict[str, str] = Field(default_factory=dict, alias="groupLabels")
    common_labels: dict[str, str] = Field(default_factory=dict, alias="commonLabels")
    common_annotations: dict[str, str] = Field(default_factory=dict, alias="commonAnnotations")
    external_url: str = Field(default="", alias="externalURL")
    alerts: list[AlertmanagerAlert] = Field(min_length=1)

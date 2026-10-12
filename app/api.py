"""API FastAPI de réception des métriques."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="System Metrics API",
    description="API de réception des métriques envoyées par les agents.",
    version="1.0.0",
)

received_metrics: list[dict[str, Any]] = []

# --- Supervision (Prometheus) ---
METRICS_RECEIVED = Counter(
    "metrics_received_total", "Nombre de payloads reçus des agents."
)
CPU_PERCENT = Gauge("agent_cpu_percent", "CPU (%) rapporté.", ["hostname"])
MEMORY_PERCENT = Gauge("agent_memory_percent", "RAM (%) rapportée.", ["hostname"])
LOAD_1M = Gauge("agent_load_1m", "Charge système 1 min.", ["hostname"])
LAST_REPORT = Gauge(
    "agent_last_report_timestamp_seconds",
    "Horodatage (epoch) du dernier envoi reçu.",
    ["hostname"],
)


def _update_gauges(data: dict[str, Any]) -> None:
    """Met à jour les jauges Prometheus à partir d'un payload agent."""
    host = str(data.get("hostname", "unknown"))
    cpu = data.get("cpu", {}).get("percent")
    mem = data.get("memory", {}).get("percent")
    load = data.get("system", {}).get("load_1m")
    if cpu is not None:
        CPU_PERCENT.labels(host).set(cpu)
    if mem is not None:
        MEMORY_PERCENT.labels(host).set(mem)
    if load is not None:
        LOAD_1M.labels(host).set(load)
    LAST_REPORT.labels(host).set_to_current_time()


class MetricsPayload(BaseModel):
    """Payload reçu depuis l'agent."""

    agent: str = Field(..., min_length=1)
    event_type: str
    data: dict[str, Any]


@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    """Retourne toutes les métriques reçues."""
    return {
        "total": len(received_metrics),
        "metrics": received_metrics,
    }


@app.get("/prometheus", include_in_schema=False)
def prometheus_metrics() -> Response:
    """Expose les métriques au format Prometheus (GET /metrics est déjà pris)."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health() -> dict[str, str]:
    """Vérifie l'état de l'API."""
    return {"status": "ok"}


@app.post("/metrics", status_code=status.HTTP_201_CREATED)
def receive_metrics(payload: MetricsPayload) -> dict[str, Any]:
    """Reçoit et stocke temporairement les métriques."""
    item = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        **payload.model_dump(),
    }
    received_metrics.append(item)
    METRICS_RECEIVED.inc()
    _update_gauges(payload.data)

    logger.info(
        "Métriques reçues de %s. Total=%s",
        payload.agent,
        len(received_metrics),
    )

    return {
        "status": "received",
        "message": "Métriques enregistrées avec succès.",
        "total_received": len(received_metrics),
    }


@app.get("/metrics/latest")
def latest_metrics() -> dict[str, Any]:
    """Retourne la dernière métrique reçue."""
    if not received_metrics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucune métrique disponible.",
        )

    return received_metrics[-1]

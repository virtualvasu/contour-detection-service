"""OpenTelemetry traces, metrics and logs for the API.

Telemetry is off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (for example to
http://127.0.0.1:4318, an OpenTelemetry Collector). Everything is then sent
there over OTLP/HTTP:

- traces: one per request, from the FastAPI and httpx instrumentation, with
  a child span for each stage of the analysis (see `stage`), so a slow
  request shows where its time went;
- metrics: request outcomes, analysis and stage durations, queueing for an
  analysis slot, water lookups, and the process's memory and CPU (the lab
  machines have 512 MB, so memory is the thing to watch);
- logs: the app's Python `logging` records, each tagged with the trace and
  span it was written in.

Each machine reports under its own host name, so traces and metrics show
which lab machine served a request. The usual OTEL_* variables apply
(OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES, OTEL_METRIC_EXPORT_INTERVAL...).

When telemetry is off, the tracer and meter below are no-ops, so the rest
of the app can use them unconditionally.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from contextlib import contextmanager

from opentelemetry import metrics, trace

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "pond-planner-api")

tracer = trace.get_tracer("pond-planner")
meter = metrics.get_meter("pond-planner")

# Analyses take from a fraction of a second to about a minute; the SDK's
# default buckets (0, 5, 10, 25... ) are meant for milliseconds.
SECONDS_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120]

requests_handled = meter.create_counter(
    "pond.requests",
    unit="{request}",
    description="Map analyses and previews handled, by endpoint and outcome "
    "(ok, invalid, busy)",
)
analysis_duration = meter.create_histogram(
    "pond.analysis.duration",
    unit="s",
    description="Time to analyze or preview a map, excluding queueing",
    explicit_bucket_boundaries_advisory=SECONDS_BUCKETS,
)
stage_duration = meter.create_histogram(
    "pond.stage.duration",
    unit="s",
    description="Time spent in each stage of the analysis",
    explicit_bucket_boundaries_advisory=SECONDS_BUCKETS,
)
slot_wait = meter.create_histogram(
    "pond.slot.wait",
    unit="s",
    description="Time a request waited for a free analysis slot",
    explicit_bucket_boundaries_advisory=SECONDS_BUCKETS,
)
slots_in_use = meter.create_up_down_counter(
    "pond.slots.in_use",
    unit="{analysis}",
    description="Analyses and previews running right now",
)
contour_points = meter.create_histogram(
    "pond.input.contour_points",
    unit="{point}",
    description="Contour points in each analyzed map (after clipping to the selected area)",
    explicit_bucket_boundaries_advisory=[1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 200_000],
)
sites_found = meter.create_counter(
    "pond.sites.found",
    unit="{site}",
    description="Pond sites suggested",
)
water_lookups = meter.create_counter(
    "pond.water.lookups",
    unit="{lookup}",
    description="OpenStreetMap water lookups, by outcome (fetched, cached, "
    "unavailable, skipped)",
)


@contextmanager
def stage(name: str):
    """Run one stage of the analysis in its own span, and record how long
    it took. Yields the span, so the stage can attach what it found."""
    start = time.perf_counter()
    with tracer.start_as_current_span(name) as span:
        try:
            yield span
        finally:
            stage_duration.record(time.perf_counter() - start, {"pond.stage": name})


def enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")) and (
        os.environ.get("OTEL_SDK_DISABLED", "").lower() != "true"
    )


def setup(app, version: str) -> None:
    """Start exporting telemetry for `app`, if it is enabled. Called once per
    worker process, as the app is imported."""
    if not enabled():
        return

    # Report HTTP requests under the stable semantic conventions
    # (http.server.request.duration, in seconds) rather than the old ones.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

    # Imported here so the SDK only loads (and takes memory) when used.
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    host = socket.gethostname()
    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": version,
            # one per worker process; host.name tells the machines apart
            "service.instance.id": f"{host}-{os.getpid()}",
            "host.name": host,
            "deployment.environment.name": os.environ.get("DEPLOY_ENV", "local"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # Every 10 s by default rather than the SDK's 60 s, so dashboards
    # follow a load test as it runs.
    interval_ms = float(os.environ.get("OTEL_METRIC_EXPORT_INTERVAL", "10000"))
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=interval_ms)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(LoggingHandler(logger_provider=logger_provider))
    # keep printing them too, as Python does on its own when no handler is set
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    app_logger.addHandler(console)

    # /health is polled and says nothing about the analysis. The ASGI
    # receive/send spans would add one span per chunk of an uploaded map.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health", exclude_spans=["receive", "send"])
    # Patches httpx's transports, so the water lookup's client (created at
    # import, before this runs) is traced too.
    HTTPXClientInstrumentor().instrument()
    # The worker's own memory and CPU; machine-wide figures would show the
    # host's, not the lab container's.
    SystemMetricsInstrumentor(
        config={
            "process.memory.usage": None,
            "process.cpu.utilization": None,
            "process.thread.count": None,
        }
    ).instrument()

    app_logger.info("Telemetry is exported to %s", os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"])

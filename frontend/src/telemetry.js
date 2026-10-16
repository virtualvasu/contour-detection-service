// OpenTelemetry tracing in the browser: the page load, and every call to the
// API. Each API call starts a trace here and passes it on in a `traceparent`
// header, so the trace continues through nginx into whichever API machine
// answered, and shows the whole request from the user's click down to each
// analysis stage.
//
// Traces are posted to /otlp, which the dev server and the nginx gateway
// pass to the OpenTelemetry Collector. Build with VITE_OTEL_TRACES_URL=off
// to leave tracing out.
import { registerInstrumentations } from '@opentelemetry/instrumentation'
import { DocumentLoadInstrumentation } from '@opentelemetry/instrumentation-document-load'
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { resourceFromAttributes } from '@opentelemetry/resources'
import { BatchSpanProcessor, WebTracerProvider } from '@opentelemetry/sdk-trace-web'

const TRACES_URL = import.meta.env.VITE_OTEL_TRACES_URL || '/otlp/v1/traces'

export function startTelemetry() {
  if (TRACES_URL === 'off') return

  const exporter = new OTLPTraceExporter({ url: new URL(TRACES_URL, window.location.origin).href })
  const provider = new WebTracerProvider({
    resource: resourceFromAttributes({ 'service.name': 'pond-planner-web' }),
    spanProcessors: [new BatchSpanProcessor(exporter)],
  })
  provider.register()

  registerInstrumentations({
    instrumentations: [
      new DocumentLoadInstrumentation(),
      // Same-origin requests (the API, under /api) get the traceparent
      // header by default; the traces' own uploads aren't traced.
      new FetchInstrumentation({ ignoreUrls: [/\/otlp\//] }),
    ],
  })
}

import { CheckCircle2, ChevronDown, Cpu, XCircle } from "lucide-react";
import { Card, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import type { ModelsResponse } from "../types";
import { categoryLabel } from "../utils/format";

function Availability({ available }: { available: boolean }) {
  return available
    ? <span className="inline-flex items-center gap-1 text-xs text-emerald-300"><CheckCircle2 className="h-3.5 w-3.5" />Available</span>
    : <span className="inline-flex items-center gap-1 text-xs text-red-300"><XCircle className="h-3.5 w-3.5" />Unavailable</span>;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid gap-1 py-2 sm:grid-cols-[170px_1fr]"><dt className="text-xs text-text-3">{label}</dt><dd className="break-words text-[13px] text-text-1">{children}</dd></div>;
}

export default function ModelInfo() {
  const { data, error, loading, reload } = useApi<ModelsResponse>("/models");
  if (loading && !data) return <Spinner />;
  if (error) return <div className="p-6"><ErrorNote message={error} onRetry={() => void reload()} /></div>;
  if (!data) return null;
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 sm:p-6">
      <PageHeader title="Model information" description="What this installation can and cannot do." />
      <div className="rounded-md border border-ink-600 bg-ink-850 p-3 text-[13px] text-text-2">{data.performance_note}</div>
      {data.object_detectors.map((m) => (
        <Card key={m.key} title={<span className="flex items-center gap-2"><Cpu className="h-4 w-4 text-text-3" />{m.name}</span>} actions={<Availability available={m.available} />}>
          {m.unavailable_reason && <div className="mb-2"><ErrorNote message={m.unavailable_reason} /></div>}
          <dl className="divide-y divide-ink-700">
            <Row label="Type">{m.type}</Row>
            <Row label="Version">{m.version}</Row>
            <Row label="Licence">{m.licence}</Row>
            <Row label="Source"><a href={m.source} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">{m.source}</a></Row>
            <Row label="Input requirements">{m.input_requirements}</Row>
            <Row label="Processing">{m.processing} Default confidence threshold: <span className="data">{m.confidence_threshold}</span>.</Row>
            <Row label="Known limitations"><ul className="list-disc space-y-1 pl-4">{m.limitations.map((l) => <li key={l}>{l}</li>)}</ul></Row>
            <Row label={`Supported categories (${m.supported_categories.length})`}>
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-accent"><ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />Show all</summary>
                <p className="mt-1 text-xs capitalize text-text-2">{m.supported_categories.join(", ")}</p>
              </details>
            </Row>
          </dl>
        </Card>
      ))}
      <Card title="Defect analysis modules" bodyClass="">
        <p className="border-b border-ink-700 px-4 py-2 text-xs text-text-3">These are transparent image-processing methods, not trained defect models. They flag unusual regions for a person to review.</p>
        <ul className="divide-y divide-ink-700">
          {data.image_processing_modules.map((m) => (
            <li key={m.key} className="px-4 py-3">
              <div className="flex items-center justify-between gap-2"><span className="text-[13px] text-text-1">{m.name}</span><Availability available={m.available} /></div>
              <p className="mt-0.5 text-xs text-text-2">{m.technique}</p>
              <p className="mt-0.5 text-xs text-text-3">Reports: {m.reports.map(categoryLabel).join(", ")}. {m.limitations.join(" ")}</p>
            </li>
          ))}
        </ul>
      </Card>
      <Card title={data.segmentation.name} actions={<Availability available={data.segmentation.available} />}>
        <p className="text-[13px] text-text-2">{data.segmentation.type}</p>
        <p className="mt-1 text-xs text-text-3">{data.segmentation.limitations.join(" ")}</p>
      </Card>
    </div>
  );
}

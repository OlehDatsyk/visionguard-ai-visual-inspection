import { AlertTriangle, ArrowLeft, Columns2, GitCompare, Layers, ScanEye, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Assistant } from "../components/Assistant";
import { clientRejection, Dropzone } from "../components/Dropzone";
import { Button, Card, ConfirmDialog, Empty, ErrorNote, PageHeader, Spinner, useToast } from "../components/ui";
import { useApi, useAuthedImage, usePolling } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import { ApiError, del, postForm } from "../services/api";
import type { Comparison as ComparisonData, Page, Project, Region } from "../types";
import { formatDate, pretty } from "../utils/format";

type Mode = "side" | "overlay" | "difference";

function PhotoPicker({ label, file, onFile }: { label: string; file: File | null; onFile: (file: File | null) => void }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) { setUrl(null); return; }
    const created = URL.createObjectURL(file);
    setUrl(created);
    return () => URL.revokeObjectURL(created);
  }, [file]);
  return (
    <div>
      <p className="label">{label}</p>
      {url && file ? (
        <div className="relative overflow-hidden rounded-lg border border-ink-600">
          <img src={url} alt={`${label} preview`} className="h-40 w-full bg-ink-900 object-contain" />
          <div className="flex items-center justify-between gap-2 border-t border-ink-700 px-2 py-1">
            <span className="truncate text-xs text-text-2">{file.name}</span>
            <Button small variant="ghost" onClick={() => onFile(null)}>Remove</Button>
          </div>
        </div>
      ) : <Dropzone compact multiple={false} label={`Choose the ${label.toLowerCase()} image`} onFiles={(files) => onFile(files[0] ?? null)} />}
    </div>
  );
}

function NewComparison({ onCreated }: { onCreated: (id: string) => void }) {
  const { workspace } = useSession();
  const projects = useApi<Page<Project>>(workspace ? `/projects?workspace_id=${workspace.id}&page_size=100` : null);
  const [before, setBefore] = useState<File | null>(null);
  const [after, setAfter] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [projectId, setProjectId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!workspace || !before || !after) return;
    const problem = clientRejection(before) ?? clientRejection(after);
    if (problem) { setError(problem); return; }
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("workspace_id", workspace.id);
    form.append("name", name);
    if (projectId) form.append("project_id", projectId);
    form.append("before", before, before.name);
    form.append("after", after, after.name);
    try {
      const created = await postForm<ComparisonData>("/comparisons", form);
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The comparison could not be started.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="New comparison">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2"><PhotoPicker label="Before" file={before} onFile={setBefore} /><PhotoPicker label="After" file={after} onFile={setAfter} /></div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label" htmlFor="cmp-name">Name (optional)</label><input id="cmp-name" className="field" maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label className="label" htmlFor="cmp-project">Attach to project (optional)</label>
            <select id="cmp-project" className="field" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">None</option>{projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        </div>
        {error && <ErrorNote message={error} />}
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-text-3">For meaningful results, photograph from the same position under the same lighting.</p>
          <Button type="submit" variant="primary" icon={GitCompare} disabled={!before || !after} busy={busy}>Compare</Button>
        </div>
      </form>
    </Card>
  );
}

function RegionOverlay({ regions, width, height }: { regions: Region[]; width: number; height: number }) {
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="absolute inset-0 h-full w-full" role="img" aria-label={`${regions.length} highlighted difference regions`}>
      {regions.map((r, i) => <rect key={i} x={r.x} y={r.y} width={r.width} height={r.height} fill="none" stroke="#ffb020" strokeWidth={Math.max(width / 500, 1.5)} />)}
    </svg>
  );
}

function ComparisonView({ comparison }: { comparison: ComparisonData }) {
  const [mode, setMode] = useState<Mode>("side");
  const [mix, setMix] = useState(0.5);
  const [showRegions, setShowRegions] = useState(true);
  const prefix = `/comparisons/${comparison.id}/file?variant=`;
  const before = useAuthedImage(`${prefix}before`);
  const aligned = useAuthedImage(`${prefix}aligned`);
  const heatmap = useAuthedImage(mode === "difference" ? `${prefix}heatmap` : null);
  const { width, height, regions, metrics } = comparison;
  const ratio = { aspectRatio: `${width} / ${height}` };
  const MODES: { key: Mode; label: string; icon: typeof Columns2 }[] = [
    { key: "side", label: "Side by side", icon: Columns2 },
    { key: "overlay", label: "Overlay", icon: Layers },
    { key: "difference", label: "Difference", icon: ScanEye },
  ];

  return (
    <div className="space-y-4">
      <Card bodyClass="p-3">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <div className="flex rounded-md bg-ink-900 p-0.5" role="group" aria-label="Comparison view">
            {MODES.map(({ key, label, icon: Icon }) => (
              <button key={key} type="button" aria-pressed={mode === key} onClick={() => setMode(key)}
                className={`flex items-center gap-1.5 rounded px-2.5 py-1 text-xs ${mode === key ? "bg-ink-700 text-text-1" : "text-text-3 hover:text-text-1"}`}><Icon className="h-3.5 w-3.5" />{label}</button>
            ))}
          </div>
          {mode === "overlay" && (
            <label className="flex items-center gap-2 text-xs text-text-2">Before
              <input aria-label="Overlay transparency" type="range" min={0} max={1} step={0.01} value={mix} onChange={(e) => setMix(Number(e.target.value))} className="w-40 accent-accent" />After
            </label>
          )}
          <label className="flex items-center gap-1.5 text-xs text-text-2"><input type="checkbox" className="accent-accent" checked={showRegions} onChange={(e) => setShowRegions(e.target.checked)} />Highlight regions ({regions.length})</label>
        </div>
        {mode === "side" && (
          <div className="grid gap-2 sm:grid-cols-2">
            {[{ title: `Before: ${comparison.before_filename}`, src: before.src }, { title: `After${metrics.alignment_status === "aligned" ? " (aligned)" : ""}: ${comparison.after_filename}`, src: aligned.src }].map(({ title, src }) => (
              <figure key={title}>
                <div className="relative overflow-hidden rounded bg-ink-900" style={ratio}>
                  {src && <img src={src} alt={title} className="block h-full w-full" />}
                  {showRegions && <RegionOverlay regions={regions} width={width} height={height} />}
                </div>
                <figcaption className="mt-1 truncate text-xs text-text-3">{title}</figcaption>
              </figure>
            ))}
          </div>
        )}
        {mode === "overlay" && (
          <div className="relative mx-auto max-w-4xl overflow-hidden rounded bg-ink-900" style={ratio}>
            {before.src && <img src={before.src} alt="Before" className="absolute inset-0 h-full w-full" />}
            {aligned.src && <img src={aligned.src} alt="After, overlaid" className="absolute inset-0 h-full w-full" style={{ opacity: mix }} />}
            {showRegions && <RegionOverlay regions={regions} width={width} height={height} />}
          </div>
        )}
        {mode === "difference" && (
          <figure className="mx-auto max-w-4xl">
            <div className="relative overflow-hidden rounded bg-ink-900" style={ratio}>
              {heatmap.src && <img src={heatmap.src} alt="Difference heatmap" className="block h-full w-full" />}
              {showRegions && <RegionOverlay regions={regions} width={width} height={height} />}
            </div>
            <figcaption className="mt-1 text-xs text-text-3">Heatmap normalised to this pair: warmer means a larger difference here, not a fixed amount.</figcaption>
          </figure>
        )}
      </Card>
      {comparison.warnings.length > 0 && (
        <div role="alert" className="rounded-md border border-amber-400/40 bg-amber-400/10 p-3">
          {comparison.warnings.map((w) => <p key={w} className="flex gap-2 text-[13px] text-amber-100"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{w}</p>)}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Metrics" className="lg:col-span-2" bodyClass="">
          <table className="w-full text-left text-[13px]">
            <tbody className="divide-y divide-ink-700">
              {([
                ["SSIM", metrics.ssim, comparison.metric_explanations.ssim],
                ["Changed area", `${metrics.changed_area_pct}%`, comparison.metric_explanations.changed_area_pct],
                ["Mean absolute difference", metrics.mean_absolute_difference, comparison.metric_explanations.mean_absolute_difference],
                ["Edge difference", `${metrics.edge_difference_pct}%`, comparison.metric_explanations.edge_difference_pct],
                ["Brightness shift", metrics.brightness_shift, comparison.metric_explanations.brightness_shift],
                ["Feature inlier ratio", metrics.feature_inlier_ratio, comparison.metric_explanations.feature_inlier_ratio],
              ] as const).map(([name, value, explanation]) => (
                <tr key={name}>
                  <td className="whitespace-nowrap px-4 py-2 align-top text-text-2">{name}</td>
                  <td className="data px-2 py-2 align-top text-text-1">{value}</td>
                  <td className="px-4 py-2 text-xs text-text-3">{explanation}</td>
                </tr>
              ))}
              <tr>
                <td className="whitespace-nowrap px-4 py-2 align-top text-text-2">Alignment</td>
                <td className="px-2 py-2 align-top text-text-1">{pretty(metrics.alignment_status)}</td>
                <td className="px-4 py-2 text-xs text-text-3">{metrics.feature_inliers} of {metrics.feature_matches} feature matches used. {metrics.overlap_pct}% of the area overlaps.</td>
              </tr>
            </tbody>
          </table>
        </Card>
        <div className="space-y-4">
          <Card title="Limitations"><ul className="list-disc space-y-1.5 pl-4 text-xs text-text-2">{comparison.limitations.map((l) => <li key={l}>{l}</li>)}</ul></Card>
          <Card title="Assistant" bodyClass=""><div className="h-80"><Assistant comparisonId={comparison.id} /></div></Card>
        </div>
      </div>
    </div>
  );
}

export default function Comparison() {
  const { comparisonId } = useParams();
  const { workspace } = useSession();
  const navigate = useNavigate();
  const toast = useToast();
  const list = useApi<Page<ComparisonData>>(!comparisonId && workspace ? `/comparisons?workspace_id=${workspace.id}` : null);
  const detail = useApi<ComparisonData>(comparisonId ? `/comparisons/${comparisonId}` : null);
  const [confirming, setConfirming] = useState(false);
  const inProgress = detail.data?.status === "queued" || detail.data?.status === "processing";
  usePolling(() => void detail.reload(), inProgress, 1000);

  if (comparisonId) {
    const c = detail.data;
    return (
      <div className="mx-auto max-w-7xl p-4 sm:p-6">
        <Link to="/comparison" className="mb-2 inline-flex items-center gap-1 text-xs text-text-3 hover:text-text-1"><ArrowLeft className="h-3 w-3" />All comparisons</Link>
        {detail.error && !c ? <ErrorNote message={detail.error === "Not found" ? "This comparison does not exist or is not in your account." : detail.error} /> : !c ? <Spinner /> : (
          <>
            <PageHeader title={c.name} description={`Created ${formatDate(c.created_at)}`} actions={<Button variant="ghost" icon={Trash2} disabled={inProgress} onClick={() => setConfirming(true)}>Delete</Button>} />
            {inProgress && <Spinner label={c.job?.stage ?? "Waiting in queue"} />}
            {c.status === "failed" && <ErrorNote message={c.job?.error_message ?? "This comparison failed."} />}
            {c.status === "completed" && <ComparisonView comparison={c} />}
            {confirming && (
              <ConfirmDialog title="Delete this comparison?" confirmLabel="Delete" onClose={() => setConfirming(false)} body="Its two images and results will be permanently deleted."
                onConfirm={() => void del(`/comparisons/${c.id}`).then(() => navigate("/comparison")).catch((e: ApiError) => toast(e.message, "error"))} />
            )}
          </>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6">
      <PageHeader title="Image comparison" description="Align two images and highlight where they differ. A difference is not proof of physical damage." />
      <div className="space-y-4">
        <NewComparison onCreated={(id) => navigate(`/comparison/${id}`)} />
        <Card title="Previous comparisons" bodyClass="">
          {list.error && <div className="p-3"><ErrorNote message={list.error} onRetry={() => void list.reload()} /></div>}
          {list.loading && !list.data ? <Spinner /> : list.data?.items.length === 0 ? <Empty icon={GitCompare} title="No comparisons yet" /> : (
            <ul className="divide-y divide-ink-700">
              {list.data?.items.map((c) => (
                <li key={c.id}><Link to={`/comparison/${c.id}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 hover:bg-ink-800">
                  <span className="min-w-0"><span className="block truncate text-[13px] text-text-1">{c.name}</span><span className="text-xs text-text-3">{formatDate(c.created_at)}</span></span>
                  {c.status === "completed"
                    ? <span className="data text-xs text-text-2">SSIM {c.metrics.ssim}, changed {c.metrics.changed_area_pct}%</span>
                    : <span className="text-xs text-text-3">{pretty(c.status)}</span>}
                </Link></li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

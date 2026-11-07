import { ArrowLeft, Archive, ArchiveRestore, Bot, CircleSlash, Download, FileText, Info, ListChecks, Pencil, Play, Plus, RefreshCw, Trash2, Boxes } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Assistant } from "../components/Assistant";
import { clientRejection, Dropzone } from "../components/Dropzone";
import { FindingDetail } from "../components/FindingPanel";
import { ImageViewer } from "../components/ImageViewer";
import { AuthedImage, BandBadge, Button, ConfirmDialog, Empty, ErrorNote, Modal, ReviewBadge, Spinner, StatusBadge, useToast } from "../components/ui";
import { useApi, usePolling } from "../hooks/useApi";
import { ApiError, del, downloadFile, patch, post, postForm } from "../services/api";
import type { Category, DetectedObject, Finding, ImageResults, InspectionImage, Job, Project, Report, UploadResult, UserSettings } from "../types";
import { categoryLabel, formatBytes, formatDateTime, pretty, scoreName } from "../utils/format";

type Tab = "findings" | "objects" | "details" | "assistant";

function JobBanner({ job, onRetry }: { job: Job; onRetry: () => void }) {
  if (job.status === "failed") {
    return (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-2 border-b border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-200">
        <span>{job.error_message ?? "Processing failed."} Attempted {job.attempts} of {job.max_attempts} times.</span>
        <Button small icon={RefreshCw} onClick={onRetry}>Retry</Button>
      </div>
    );
  }
  if (job.status === "completed") return null;
  const pct = job.items_total ? (job.items_done / job.items_total) * 100 : 0;
  return (
    <div role="status" className="border-b border-ink-700 bg-ink-850 px-4 py-2">
      <div className="flex items-center justify-between gap-2 text-xs text-text-2">
        <span className="truncate">{job.stage}{job.attempts > 1 ? ` (attempt ${job.attempts})` : ""}</span>
        <span className="data shrink-0">{job.items_done} of {job.items_total} images</span>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded bg-ink-700"><div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

function FindingRow({ finding, selected, onSelect }: { finding: Finding; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected}
      className={`w-full rounded-md border px-2.5 py-2 text-left transition-colors ${selected ? "border-accent bg-accent-dim/30" : "border-ink-700 hover:border-ink-600 hover:bg-ink-800"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[13px] text-text-1">{categoryLabel(finding.category)}</span>
        {finding.score_type !== "image_quality" && <span className="data text-xs text-text-2" title={scoreName(finding.score_type)}>{finding.score.toFixed(2)}</span>}
      </div>
      <div className="mt-1 flex flex-wrap gap-1"><BandBadge band={finding.confidence_band} /><ReviewBadge status={finding.review_status} /></div>
    </button>
  );
}

function FindingGroup({ title, hint, items, selectedId, onSelect }: { title: string; hint: string; items: Finding[]; selectedId: string | null; onSelect: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <section>
      <h3 className="eyebrow">{title} ({items.length})</h3>
      <p className="mb-1.5 text-xs text-text-3">{hint}</p>
      <div className="space-y-1.5">{items.map((f) => <FindingRow key={f.id} finding={f} selected={f.id === selectedId} onSelect={() => onSelect(f.id)} />)}</div>
    </section>
  );
}

function ObjectDetail({ object }: { object: DetectedObject }) {
  return (
    <dl className="grid grid-cols-2 gap-y-1 text-xs">
      <dt className="text-text-3">Model confidence</dt><dd className="data text-right text-text-1">{object.confidence.toFixed(3)}</dd>
      <dt className="text-text-3">Location (x, y, w, h)</dt><dd className="data text-right text-text-1">{[object.x, object.y, object.width, object.height].map((v) => Math.round(v)).join(", ")}</dd>
      <dt className="text-text-3">Model</dt><dd className="text-right text-text-1">{object.model_name}</dd>
      <dt className="text-text-3">Outline</dt><dd className="text-right text-text-1">{object.polygon ? "GrabCut, approximate" : "Box only"}</dd>
    </dl>
  );
}

export default function InspectionWorkspace() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const project = useApi<Project>(`/projects/${projectId}`);
  const images = useApi<InspectionImage[]>(`/projects/${projectId}/images`);
  const jobs = useApi<Job[]>(`/projects/${projectId}/jobs`);
  const reports = useApi<{ items: Report[] }>(project.data ? `/reports?workspace_id=${project.data.workspace_id}&project_id=${projectId}` : null);
  const categories = useApi<Category[]>("/categories");
  const settings = useApi<UserSettings>("/settings");
  const [imageId, setImageId] = useState<string | null>(null);
  const results = useApi<ImageResults>(imageId ? `/images/${imageId}/results` : null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("findings");
  const [dialog, setDialog] = useState<null | "edit" | "report" | "delete" | "add" | "reanalyse" | "deleteImage">(null);
  const [busy, setBusy] = useState(false);

  const job = jobs.data?.[0] ?? null;
  const active = job?.status === "queued" || job?.status === "running";

  const refreshAll = useCallback(() => {
    void project.reload();
    void images.reload();
    void jobs.reload();
    void results.reload();
  }, [project.reload, images.reload, jobs.reload, results.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  usePolling(() => {
    void jobs.reload();
    void images.reload();
  }, active);

  // When a job finishes, pull fresh results and status once.
  const [wasActive, setWasActive] = useState(false);
  useEffect(() => {
    if (wasActive && !active) refreshAll();
    setWasActive(active);
  }, [active, wasActive, refreshAll]);

  useEffect(() => {
    if (!images.data) return;
    if (!imageId || !images.data.some((i) => i.id === imageId)) setImageId(images.data[0]?.id ?? null);
  }, [images.data, imageId]);
  useEffect(() => setSelectedId(null), [imageId]);

  const current = results.data?.image.id === imageId ? results.data : null;
  const image = images.data?.find((i) => i.id === imageId) ?? null;
  const findings = current?.findings ?? [];
  const groups = useMemo(() => ({
    defects: findings.filter((f) => f.finding_type === "potential_defect" && f.confidence_band !== "unverified"),
    weak: findings.filter((f) => f.finding_type === "potential_defect" && f.confidence_band === "unverified"),
    manual: findings.filter((f) => f.finding_type === "manual_inspection"),
  }), [findings]);
  const selectedFinding = findings.find((f) => f.id === selectedId) ?? null;
  const selectedObject = current?.objects.find((o) => o.id === selectedId) ?? null;
  const unanalysed = images.data?.filter((i) => i.status !== "analysed").length ?? 0;
  const archived = project.data?.status === "archived";
  const processing = project.data?.status === "processing" || active;

  const selectItem = (id: string | null) => {
    setSelectedId(id);
    if (id && findings.some((f) => f.id === id)) setTab("findings");
    if (id && current?.objects.some((o) => o.id === id)) setTab("objects");
  };

  const run = async (reanalyze = false) => {
    setBusy(true);
    try {
      await post<Job>(`/projects/${projectId}/analyze`, { reanalyze });
      setDialog(null);
      refreshAll();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "The analysis could not start.", "error");
    } finally {
      setBusy(false);
    }
  };

  const retry = async () => {
    if (!job) return;
    try {
      await post(`/jobs/${job.id}/retry`);
      refreshAll();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "The job could not be retried.", "error");
    }
  };

  if (project.error && !project.data) {
    return <div className="p-6"><ErrorNote message={project.error === "Not found" ? "This inspection does not exist or is not in your account." : project.error} /><Link to="/inspections" className="mt-3 inline-block text-sm text-accent">Back to history</Link></div>;
  }
  if (!project.data) return <Spinner />;
  const p = project.data;
  const categoryName = categories.data?.find((c) => c.key === p.category)?.label ?? p.category;

  const TABS: { key: Tab; label: string; icon: typeof ListChecks; count?: number }[] = [
    { key: "findings", label: "Findings", icon: ListChecks, count: findings.length },
    { key: "objects", label: "Objects", icon: Boxes, count: current?.objects.length },
    { key: "details", label: "Details", icon: Info },
    { key: "assistant", label: "Assistant", icon: Bot },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-ink-700 bg-ink-900 px-4 py-2.5">
        <Link to="/inspections" aria-label="Back to history" className="rounded p-1 text-text-3 hover:bg-ink-800 hover:text-text-1"><ArrowLeft className="h-4 w-4" /></Link>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-[15px]">{p.name}</h1><StatusBadge status={p.status} />
          </div>
          <p className="truncate text-xs text-text-3">{categoryName}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {unanalysed > 0 && !processing && !archived && <Button small variant="primary" icon={Play} busy={busy} onClick={() => void run()}>Run analysis</Button>}
          {!archived && <Button small icon={Plus} disabled={processing} onClick={() => setDialog("add")}>Add images</Button>}
          {!archived && unanalysed < (images.data?.length ?? 0) && <Button small icon={RefreshCw} disabled={processing} onClick={() => setDialog("reanalyse")}>Re-analyse</Button>}
          <Button small icon={FileText} disabled={processing || !images.data?.some((i) => i.status === "analysed")} onClick={() => setDialog("report")}>Generate report</Button>
          <Button small variant="ghost" icon={Pencil} aria-label="Edit project" title="Edit project" onClick={() => setDialog("edit")} />
          <Button small variant="ghost" icon={archived ? ArchiveRestore : Archive} aria-label={archived ? "Unarchive" : "Archive"} title={archived ? "Unarchive" : "Archive"} disabled={processing}
            onClick={() => void patch<Project>(`/projects/${projectId}`, { archived: !archived }).then(() => { void project.reload(); toast(archived ? "Project restored." : "Project archived."); }).catch((e: ApiError) => toast(e.message, "error"))} />
          <Button small variant="ghost" icon={Trash2} aria-label="Delete project" title="Delete project" disabled={processing} onClick={() => setDialog("delete")} />
        </div>
      </header>
      {job && <JobBanner job={job} onRetry={() => void retry()} />}

      {images.data && images.data.length === 0 ? (
        <div className="p-6">
          <Empty icon={Plus} title="This project has no images" action={!archived && <Button variant="primary" icon={Plus} onClick={() => setDialog("add")}>Add images</Button>}>
            Add images, then run the analysis.
          </Empty>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <div className="flex min-h-[55vh] min-w-0 flex-1 flex-col lg:min-h-0">
            <div className="min-h-0 flex-1">
              {image ? (
                <ImageViewer key={image.id} imageId={image.id} width={image.metadata.display_width} height={image.metadata.display_height}
                  hasProcessed={image.has_processed} objects={current?.objects ?? []} findings={findings} selectedId={selectedId} onSelect={selectItem}
                  initialOpacity={settings.data?.overlay_opacity} />
              ) : <Spinner />}
            </div>
            {images.data && images.data.length > 0 && (
              <div className="flex gap-2 overflow-x-auto border-t border-ink-700 bg-ink-900 p-2" role="listbox" aria-label="Images in this project">
                {images.data.map((i) => (
                  <button key={i.id} type="button" role="option" aria-selected={i.id === imageId} onClick={() => setImageId(i.id)} title={i.filename}
                    className={`relative h-14 w-20 shrink-0 overflow-hidden rounded border-2 ${i.id === imageId ? "border-accent" : "border-transparent hover:border-ink-600"}`}>
                    <AuthedImage path={`/images/${i.id}/file?variant=thumbnail`} alt={i.filename} className="h-full w-full object-cover" />
                    {i.status !== "analysed" && <span className="absolute inset-x-0 bottom-0 bg-black/70 text-center text-[9px] text-white">Not analysed</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <aside className="flex min-h-[420px] w-full shrink-0 flex-col border-t border-ink-700 bg-ink-900 lg:min-h-0 lg:w-[360px] lg:border-l lg:border-t-0">
            <div role="tablist" className="flex border-b border-ink-700">
              {TABS.map(({ key, label, icon: Icon, count }) => (
                <button key={key} role="tab" type="button" aria-selected={tab === key} onClick={() => setTab(key)}
                  className={`flex flex-1 items-center justify-center gap-1 border-b-2 px-1 py-2 text-xs ${tab === key ? "border-accent text-text-1" : "border-transparent text-text-3 hover:text-text-1"}`}>
                  <Icon className="h-3.5 w-3.5" />{label}{count !== undefined && count > 0 ? <span className="data text-text-3">{count}</span> : null}
                </button>
              ))}
            </div>
            {tab === "assistant" ? (
              <div className="min-h-0 flex-1"><Assistant projectId={projectId} /></div>
            ) : (
              <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
                {tab === "findings" && (
                  image?.status !== "analysed" ? <p className="text-sm text-text-3">{processing ? "This image is waiting for or undergoing analysis." : "This image has not been analysed yet."}</p> : (
                    <>
                      {selectedFinding && <div className="rounded-md border border-accent/50 bg-ink-850 p-3"><FindingDetail finding={selectedFinding} onChange={() => void results.reload().then(() => project.reload())} /></div>}
                      {findings.length === 0 && <p className="rounded-md border border-ink-700 p-3 text-[13px] text-text-2">No findings were reported for this image. This does not prove that the surface is free from defects.</p>}
                      <FindingGroup title="Potential defects" hint="Unverified until you review them." items={groups.defects} selectedId={selectedId} onSelect={selectItem} />
                      <FindingGroup title="Insufficient confidence" hint="Weak signals. Do not rely on these without looking." items={groups.weak} selectedId={selectedId} onSelect={selectItem} />
                      <FindingGroup title="Manual inspection needed" hint="The analysis could not see these areas properly." items={groups.manual} selectedId={selectedId} onSelect={selectItem} />
                      {image.analysis_notes.length > 0 && (
                        <section><h3 className="eyebrow mb-1">Analysis notes</h3><ul className="space-y-1 text-xs text-text-2">{image.analysis_notes.map((n, i) => <li key={i} className="flex gap-1.5"><Info className="mt-0.5 h-3 w-3 shrink-0 text-text-3" />{n}</li>)}</ul></section>
                      )}
                      {image.unsupported_checks.length > 0 && (
                        <section><h3 className="eyebrow mb-1">Not assessed</h3><ul className="space-y-1 text-xs text-text-3">{image.unsupported_checks.map((u) => <li key={u.check} className="flex gap-1.5"><CircleSlash className="mt-0.5 h-3 w-3 shrink-0" /><span><span className="text-text-2">{pretty(u.check)}.</span> {u.reason}</span></li>)}</ul></section>
                      )}
                    </>
                  )
                )}
                {tab === "objects" && (
                  (current?.objects.length ?? 0) === 0 ? <p className="text-sm text-text-3">{image?.status === "analysed" ? "No supported objects were detected. The detector only knows 80 everyday COCO categories." : "This image has not been analysed yet."}</p> : (
                    <div className="space-y-1.5">
                      <p className="text-xs text-text-3">Objects recognised by the detector. A detected object is not a defect.</p>
                      {current?.objects.map((o) => (
                        <div key={o.id} className={`rounded-md border ${o.id === selectedId ? "border-accent bg-accent-dim/30" : "border-ink-700"}`}>
                          <button type="button" className="w-full px-2.5 py-2 text-left" aria-pressed={o.id === selectedId} onClick={() => setSelectedId(o.id)}>
                            <div className="flex items-baseline justify-between"><span className="text-[13px] capitalize text-text-1">{o.label}</span><span className="data text-xs text-text-2">{o.confidence.toFixed(2)}</span></div>
                            <div className="mt-1"><BandBadge band={o.confidence_band} /></div>
                          </button>
                          {o.id === selectedId && selectedObject && <div className="border-t border-ink-700 p-2.5"><ObjectDetail object={selectedObject} /></div>}
                        </div>
                      ))}
                    </div>
                  )
                )}
                {tab === "details" && image && (
                  <>
                    <section>
                      <h3 className="eyebrow mb-1">Image</h3>
                      <p className="break-all text-[13px] text-text-1">{image.filename}</p>
                      {image.description && <p className="mt-1 text-xs text-text-2">{image.description}</p>}
                      <dl className="mt-2 grid grid-cols-2 gap-y-1 text-xs">
                        <dt className="text-text-3">Dimensions</dt><dd className="data text-right text-text-1">{image.metadata.width} x {image.metadata.height}</dd>
                        <dt className="text-text-3">Format</dt><dd className="text-right text-text-1">{image.metadata.file_format}</dd>
                        <dt className="text-text-3">File size</dt><dd className="data text-right text-text-1">{formatBytes(image.metadata.file_size)}</dd>
                        <dt className="text-text-3">Uploaded</dt><dd className="text-right text-text-1">{formatDateTime(image.created_at)}</dd>
                        <dt className="text-text-3">Analysed</dt><dd className="text-right text-text-1">{image.analysed_at ? formatDateTime(image.analysed_at) : "Not yet"}</dd>
                        <dt className="text-text-3">Identifier</dt><dd className="data truncate text-right text-text-1" title={image.id}>{image.id.slice(0, 13)}</dd>
                        <dt className="text-text-3">SHA-256</dt><dd className="data truncate text-right text-text-1" title={image.metadata.checksum_sha256}>{image.metadata.checksum_sha256.slice(0, 16)}</dd>
                      </dl>
                      {image.metadata.had_gps && <p className="mt-2 rounded border border-amber-400/30 bg-amber-400/10 p-2 text-xs text-amber-100">The original upload contains GPS data. It is not extracted, shown or put in reports, but stays in the original file you can download.</p>}
                      <div className="mt-2 flex gap-1.5">
                        <Button small icon={Download} onClick={() => void downloadFile(`/images/${image.id}/file?variant=original`, image.filename).catch(() => toast("The download failed.", "error"))}>Original</Button>
                        <Button small variant="danger" icon={Trash2} disabled={processing} onClick={() => setDialog("deleteImage")}>Delete image</Button>
                      </div>
                    </section>
                    {Object.keys(image.metadata.quality).length > 0 && (
                      <section>
                        <h3 className="eyebrow mb-1">Measured image quality</h3>
                        <dl className="grid grid-cols-2 gap-y-1 text-xs">
                          {Object.entries(image.metadata.quality).filter(([, v]) => typeof v === "number").map(([k, v]) => (
                            <div key={k} className="contents"><dt className="text-text-3">{pretty(k)}</dt><dd className="data text-right text-text-1">{String(v)}</dd></div>
                          ))}
                        </dl>
                      </section>
                    )}
                    <section>
                      <h3 className="eyebrow mb-1">Project</h3>
                      {p.description && <p className="mb-1 text-xs text-text-2">{p.description}</p>}
                      <p className="whitespace-pre-wrap text-xs text-text-3">{p.notes || "No notes yet. Use Edit project to add them."}</p>
                    </section>
                    <section>
                      <h3 className="eyebrow mb-1">Reports</h3>
                      {reports.data?.items.length ? (
                        <ul className="space-y-1">{reports.data.items.map((r) => (
                          <li key={r.id} className="flex items-center justify-between gap-2 text-xs"><span className="truncate text-text-2">{r.title}</span>
                            <Button small variant="ghost" icon={Download} aria-label={`Download ${r.title}`} onClick={() => void downloadFile(`/reports/${r.id}/file?download=true`, "visionguard-report.pdf").catch(() => toast("The download failed.", "error"))} /></li>
                        ))}</ul>
                      ) : <p className="text-xs text-text-3">No reports yet.</p>}
                    </section>
                  </>
                )}
              </div>
            )}
          </aside>
        </div>
      )}

      {dialog === "edit" && <EditDialog project={p} categories={categories.data ?? []} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); void project.reload(); }} />}
      {dialog === "report" && <ReportDialog project={p} onClose={() => setDialog(null)} onDone={() => { setDialog(null); void reports.reload(); }} />}
      {dialog === "add" && <AddImagesDialog projectId={projectId} onClose={() => setDialog(null)} onDone={() => { setDialog(null); refreshAll(); }} />}
      {dialog === "reanalyse" && (
        <ConfirmDialog title="Re-analyse all images?" confirmLabel="Re-analyse" busy={busy} onClose={() => setDialog(null)} onConfirm={() => void run(true)}
          body="Current findings and their review decisions for this project will be replaced by new results." />
      )}
      {dialog === "delete" && (
        <ConfirmDialog title="Delete this project?" confirmLabel="Delete project" busy={busy} onClose={() => setDialog(null)}
          onConfirm={() => { setBusy(true); void del(`/projects/${projectId}`).then(() => navigate("/inspections")).catch((e: ApiError) => toast(e.message, "error")).finally(() => setBusy(false)); }}
          body={`"${p.name}" with its images, results and reports will be permanently deleted.`} />
      )}
      {dialog === "deleteImage" && image && (
        <ConfirmDialog title="Delete this image?" confirmLabel="Delete image" busy={busy} onClose={() => setDialog(null)}
          onConfirm={() => { setBusy(true); void del(`/images/${image.id}`).then(() => { setDialog(null); refreshAll(); }).catch((e: ApiError) => toast(e.message, "error")).finally(() => setBusy(false)); }}
          body={`"${image.filename}" and its findings will be permanently deleted.`} />
      )}
    </div>
  );
}

function EditDialog({ project, categories, onClose, onSaved }: { project: Project; categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);
  const [category, setCategory] = useState(project.category);
  const [notes, setNotes] = useState(project.notes);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await patch(`/projects/${project.id}`, { name, description, category, notes });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The changes could not be saved.");
    }
  };
  return (
    <Modal title="Edit project" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        {error && <ErrorNote message={error} />}
        <div><label className="label" htmlFor="edit-name">Name</label><input id="edit-name" className="field" required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="label" htmlFor="edit-category">Category</label>
          <select id="edit-category" className="field" value={category} onChange={(e) => setCategory(e.target.value)}>{categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>
          {category !== project.category && <p className="mt-1 text-xs text-text-3">Applies to images analysed from now on. Use Re-analyse to update existing results.</p>}
        </div>
        <div><label className="label" htmlFor="edit-description">Description</label><textarea id="edit-description" className="field" rows={2} maxLength={4000} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
        <div><label className="label" htmlFor="edit-notes">Notes</label><textarea id="edit-notes" className="field" rows={4} maxLength={8000} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        <div className="flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary">Save</Button></div>
      </form>
    </Modal>
  );
}

function ReportDialog({ project, onClose, onDone }: { project: Project; onClose: () => void; onDone: () => void }) {
  const [title, setTitle] = useState(`Inspection report: ${project.name}`);
  const [notes, setNotes] = useState(project.notes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const report = await post<Report>(`/projects/${project.id}/reports`, { title, final_notes: notes });
      onDone();
      navigate(`/reports?open=${report.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The report could not be generated.");
      setBusy(false);
    }
  };
  return (
    <Modal title="Generate report" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        {error && <ErrorNote message={error} />}
        <div><label className="label" htmlFor="report-title">Title</label><input id="report-title" className="field" required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></div>
        <div><label className="label" htmlFor="report-notes">Final inspection notes</label><textarea id="report-notes" className="field" rows={4} maxLength={8000} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        {project.unreviewed_count > 0 && <p className="text-xs text-amber-200">{project.unreviewed_count} findings have not been reviewed. They will be listed as not reviewed.</p>}
        <div className="flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="primary" busy={busy}>Generate PDF</Button></div>
      </form>
    </Modal>
  );
}

function AddImagesDialog({ projectId, onClose, onDone }: { projectId: string; onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const toast = useToast();
  const upload = async (files: File[]) => {
    const local = files.map((f) => [f, clientRejection(f)] as const);
    const usable = local.filter(([, problem]) => !problem).map(([f]) => f);
    const issues = local.filter(([, problem]) => problem).map(([f, problem]) => `${f.name}: ${problem}`);
    setProblems(issues);
    if (usable.length === 0) return;
    setBusy(true);
    const form = new FormData();
    usable.forEach((f) => form.append("files", f, f.name));
    try {
      const result = await postForm<UploadResult>(`/projects/${projectId}/images`, form);
      if (result.rejected.length) {
        setProblems([...issues, ...result.rejected.map((r) => `${r.filename}: ${r.reason}`)]);
        setBusy(false);
        return;
      }
      toast(`${result.accepted.length} image(s) added. Choose Run analysis to process them.`);
      onDone();
    } catch (err) {
      setProblems([...issues, err instanceof ApiError ? err.message : "The upload failed."]);
      setBusy(false);
    }
  };
  return (
    <Modal title="Add images" onClose={onClose}>
      {busy ? <Spinner label="Uploading and validating" /> : <Dropzone onFiles={(f) => void upload(f)} />}
      {problems.length > 0 && <ul className="mt-3 space-y-1 text-xs text-red-200">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>}
    </Modal>
  );
}

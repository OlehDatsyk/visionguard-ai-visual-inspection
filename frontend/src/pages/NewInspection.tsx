import { CircleSlash, ScanLine, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { clientRejection, Dropzone } from "../components/Dropzone";
import { Button, Card, ErrorNote, PageHeader, useToast } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import { ApiError, post, postForm } from "../services/api";
import type { Category, Job, Page, Project, UploadResult, UserSettings } from "../types";
import { formatBytes, pretty } from "../utils/format";

interface Draft { id: string; file: File; url: string; description: string; problem: string | null }

export default function NewInspection() {
  const { workspace } = useSession();
  const navigate = useNavigate();
  const toast = useToast();
  const [params] = useSearchParams();
  const categories = useApi<Category[]>("/categories");
  const settings = useApi<UserSettings>("/settings");
  const projects = useApi<Page<Project>>(workspace ? `/projects?workspace_id=${workspace.id}&page_size=100` : null);
  const [target, setTarget] = useState(params.get("project") ?? "new");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [rejected, setRejected] = useState<{ filename: string; reason: string }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!category && categories.data?.length) setCategory(settings.data?.default_category ?? categories.data[0].key);
  }, [categories.data, settings.data, category]);
  useEffect(() => () => drafts.forEach((d) => URL.revokeObjectURL(d.url)), []); // eslint-disable-line react-hooks/exhaustive-deps

  const usable = useMemo(() => drafts.filter((d) => !d.problem), [drafts]);
  const existing = projects.data?.items.filter((p) => p.status !== "archived" && p.status !== "processing") ?? [];
  const selectedProject = existing.find((p) => p.id === target);
  const selectedCategory = categories.data?.find((c) => c.key === (selectedProject?.category ?? category));

  const addFiles = (files: File[]) => {
    setDrafts((all) => [...all, ...files.map((file) => ({
      id: crypto.randomUUID(), file, url: URL.createObjectURL(file), description: "", problem: clientRejection(file),
    }))]);
  };
  const remove = (id: string) => setDrafts((all) => {
    const item = all.find((d) => d.id === id);
    if (item) URL.revokeObjectURL(item.url);
    return all.filter((d) => d.id !== id);
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!workspace || usable.length === 0) return;
    setError(null);
    setRejected([]);
    try {
      setBusy("Creating inspection");
      const projectId = target !== "new" ? target : (await post<Project>("/projects", { workspace_id: workspace.id, name, description, category })).id;
      setBusy(`Uploading ${usable.length} image${usable.length > 1 ? "s" : ""}`);
      const form = new FormData();
      usable.forEach((d) => {
        form.append("files", d.file, d.file.name);
        form.append("descriptions", d.description);
      });
      const result = await postForm<UploadResult>(`/projects/${projectId}/images`, form);
      setRejected(result.rejected);
      setTarget(projectId);
      setDrafts([]);
      void projects.reload();
      if (result.accepted.length === 0) {
        setError("No images were accepted. Fix the problems below and try again.");
        return;
      }
      setBusy("Starting analysis");
      await post<Job>(`/projects/${projectId}/analyze`, {});
      result.rejected.forEach((r) => toast(`${r.filename} was skipped: ${r.reason}`, "error"));
      navigate(`/inspections/${projectId}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The inspection could not be started.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-6">
      <PageHeader title="New inspection" description="Describe the inspection, add images, then run the analysis. Originals are stored unchanged." />
      <form onSubmit={submit} className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <Card title="Images">
            <Dropzone onFiles={addFiles} />
            {drafts.length > 0 && (
              <ul className="mt-3 divide-y divide-ink-700 rounded-md border border-ink-700">
                {drafts.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 p-2">
                    <img src={d.url} alt={`Preview of ${d.file.name}`} className="h-14 w-20 shrink-0 rounded bg-ink-800 object-cover" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-[13px] text-text-1">{d.file.name}</span>
                        <span className="data shrink-0 text-xs text-text-3">{formatBytes(d.file.size)}</span>
                      </div>
                      {d.problem
                        ? <p className="mt-1 text-xs text-red-300">{d.problem} This file will not be uploaded.</p>
                        : <input aria-label={`Description for ${d.file.name}`} className="field mt-1 !py-1 text-xs" maxLength={2000} placeholder="Description (optional)" value={d.description}
                            onChange={(e) => setDrafts((all) => all.map((x) => x.id === d.id ? { ...x, description: e.target.value } : x))} />}
                    </div>
                    <Button small variant="ghost" icon={Trash2} aria-label={`Remove ${d.file.name}`} onClick={() => remove(d.id)} />
                  </li>
                ))}
              </ul>
            )}
            {rejected.length > 0 && (
              <ul className="mt-3 space-y-1 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200">
                {rejected.map((r, i) => <li key={i}><strong>{r.filename}:</strong> {r.reason}</li>)}
              </ul>
            )}
          </Card>
        </div>
        <div className="space-y-4 lg:col-span-2">
          <Card title="Details">
            <div className="space-y-3">
              <div>
                <label className="label" htmlFor="target">Inspection project</label>
                <select id="target" className="field" value={target} onChange={(e) => setTarget(e.target.value)}>
                  <option value="new">Create a new project</option>
                  {existing.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              {target === "new" && (
                <>
                  <div>
                    <label className="label" htmlFor="name">Project name</label>
                    <input id="name" className="field" required maxLength={160} value={name} onChange={(e) => setName(e.target.value)} placeholder="Line 4 housing batch" />
                  </div>
                  <div>
                    <label className="label" htmlFor="category">Inspection category</label>
                    <select id="category" className="field" value={category} onChange={(e) => setCategory(e.target.value)}>
                      {categories.data?.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label" htmlFor="description">Description (optional)</label>
                    <textarea id="description" className="field" rows={2} maxLength={4000} value={description} onChange={(e) => setDescription(e.target.value)} />
                  </div>
                </>
              )}
            </div>
          </Card>
          {selectedCategory && (
            <Card title="What this category checks">
              <p className="eyebrow mb-1">Runs on every image</p>
              <ul className="mb-3 space-y-0.5 text-[13px] text-text-2">
                <li>Object detection (80 everyday COCO classes)</li>
                {selectedCategory.checks.map((c) => <li key={c}>{c}</li>)}
              </ul>
              {selectedCategory.not_assessed.length > 0 && (
                <>
                  <p className="eyebrow mb-1">Cannot be reliably assessed</p>
                  <ul className="space-y-1 text-xs text-text-3">
                    {selectedCategory.not_assessed.map((n) => (
                      <li key={n.check} className="flex gap-1.5"><CircleSlash className="mt-0.5 h-3 w-3 shrink-0" /><span><span className="text-text-2">{pretty(n.check)}.</span> {n.reason}</span></li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
          )}
          {error && <ErrorNote message={error} />}
          <Button type="submit" variant="primary" icon={ScanLine} className="w-full" disabled={usable.length === 0 || (target === "new" && !name.trim())} busy={busy !== null}>
            {busy ?? `Run analysis on ${usable.length} image${usable.length === 1 ? "" : "s"}`}
          </Button>
        </div>
      </form>
    </div>
  );
}

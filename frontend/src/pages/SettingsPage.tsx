import { FlaskConical, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Card, ConfirmDialog, DemoBadge, ErrorNote, Modal, PageHeader, useToast } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import { ApiError, del, hasToken, patch, post, put, setToken } from "../services/api";
import type { AssistantStatus, Category, TokenResponse, User, UserSettings, Workspace } from "../types";

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

function Profile() {
  const { user, setUser } = useSession();
  const toast = useToast();
  const [name, setName] = useState(user?.full_name ?? "");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setUser(await patch<User>("/users/me", { full_name: name }));
      toast("Profile saved.");
    } catch (err) { toast(errorText(err, "The profile could not be saved."), "error"); }
  };
  return (
    <Card title="Profile">
      <form onSubmit={save} className="space-y-3">
        <div><label className="label" htmlFor="profile-email">E-mail</label><input id="profile-email" className="field opacity-70" value={user?.email ?? ""} disabled /></div>
        <div><label className="label" htmlFor="profile-name">Full name</label><input id="profile-name" className="field" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></div>
        <Button type="submit">Save profile</Button>
      </form>
    </Card>
  );
}

function PasswordForm() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const result = await post<TokenResponse>("/users/me/password", { current_password: current, new_password: next });
      setToken(result.access_token);
      setCurrent("");
      setNext("");
      toast("Password changed. Other sessions were signed out.");
    } catch (err) { toast(errorText(err, "The password could not be changed."), "error"); }
  };
  return (
    <Card title="Password">
      <form onSubmit={save} className="space-y-3">
        <div><label className="label" htmlFor="pw-current">Current password</label><input id="pw-current" type="password" autoComplete="current-password" className="field" required value={current} onChange={(e) => setCurrent(e.target.value)} /></div>
        <div><label className="label" htmlFor="pw-new">New password</label><input id="pw-new" type="password" autoComplete="new-password" className="field" required minLength={10} maxLength={128} value={next} onChange={(e) => setNext(e.target.value)} /></div>
        <Button type="submit">Change password</Button>
      </form>
    </Card>
  );
}

function Preferences() {
  const toast = useToast();
  const settings = useApi<UserSettings>("/settings");
  const categories = useApi<Category[]>("/categories");
  const [form, setForm] = useState<UserSettings | null>(null);
  useEffect(() => { if (settings.data) setForm(settings.data); }, [settings.data]);
  if (!form) return null;
  const save = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await put("/settings", form);
      toast("Preferences saved.");
    } catch (err) { toast(errorText(err, "The preferences could not be saved."), "error"); }
  };
  return (
    <Card title="Analysis preferences">
      <form onSubmit={save} className="space-y-3">
        <div><label className="label" htmlFor="pref-category">Default inspection category</label>
          <select id="pref-category" className="field" value={form.default_category ?? ""} onChange={(e) => setForm({ ...form, default_category: e.target.value || null })}>
            <option value="">No default</option>{categories.data?.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="pref-threshold">Object detection threshold: <span className="data">{form.detector_confidence_threshold.toFixed(2)}</span></label>
          <input id="pref-threshold" type="range" min={0.05} max={0.95} step={0.05} className="w-full accent-accent" value={form.detector_confidence_threshold} onChange={(e) => setForm({ ...form, detector_confidence_threshold: Number(e.target.value) })} />
          <p className="text-xs text-text-3">A lower value shows more detections, including less certain ones. Applies to future analyses.</p>
        </div>
        <div>
          <label className="label" htmlFor="pref-opacity">Default mask opacity: <span className="data">{Math.round(form.overlay_opacity * 100)}%</span></label>
          <input id="pref-opacity" type="range" min={0} max={1} step={0.05} className="w-full accent-accent" value={form.overlay_opacity} onChange={(e) => setForm({ ...form, overlay_opacity: Number(e.target.value) })} />
        </div>
        <Button type="submit">Save preferences</Button>
      </form>
    </Card>
  );
}

function Workspaces() {
  const { workspaces, workspace, reloadWorkspaces, selectWorkspace } = useSession();
  const toast = useToast();
  const [deleting, setDeleting] = useState<Workspace | null>(null);
  const [renaming, setRenaming] = useState<Workspace | null>(null);
  const [name, setName] = useState("");
  const remove = async () => {
    if (!deleting) return;
    try {
      await del(`/workspaces/${deleting.id}`);
      setDeleting(null);
      await reloadWorkspaces();
      toast("Workspace deleted.");
    } catch (err) { setDeleting(null); toast(errorText(err, "The workspace could not be deleted."), "error"); }
  };
  const rename = async (event: FormEvent) => {
    event.preventDefault();
    if (!renaming) return;
    try {
      await patch(`/workspaces/${renaming.id}`, { name });
      setRenaming(null);
      await reloadWorkspaces();
    } catch (err) { toast(errorText(err, "The workspace could not be renamed."), "error"); }
  };
  return (
    <Card title="Workspaces" bodyClass="">
      <ul className="divide-y divide-ink-700">
        {workspaces.map((w) => (
          <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
            <span className="flex min-w-0 items-center gap-2 text-[13px] text-text-1"><span className="truncate">{w.name}</span>{w.is_demo && <DemoBadge />}{w.id === workspace?.id && <span className="text-xs text-text-3">Current</span>}</span>
            <span className="flex gap-1">
              {w.id !== workspace?.id && <Button small variant="ghost" onClick={() => selectWorkspace(w.id)}>Switch</Button>}
              {!w.is_demo && <Button small variant="ghost" onClick={() => { setRenaming(w); setName(w.name); }}>Rename</Button>}
              <Button small variant="ghost" icon={Trash2} aria-label={`Delete ${w.name}`} onClick={() => setDeleting(w)} />
            </span>
          </li>
        ))}
      </ul>
      {deleting && <ConfirmDialog title="Delete this workspace?" confirmLabel="Delete workspace" onClose={() => setDeleting(null)} onConfirm={() => void remove()} body={`"${deleting.name}" with all its projects, images and reports will be permanently deleted.`} />}
      {renaming && (
        <Modal title="Rename workspace" onClose={() => setRenaming(null)}>
          <form onSubmit={rename}>
            <label className="label" htmlFor="rename-workspace">Name</label>
            <input id="rename-workspace" className="field" required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
            <div className="mt-4 flex justify-end gap-2"><Button onClick={() => setRenaming(null)}>Cancel</Button><Button type="submit" variant="primary">Save</Button></div>
          </form>
        </Modal>
      )}
    </Card>
  );
}

function DemoMode() {
  const { workspaces, reloadWorkspaces, selectWorkspace } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const existing = workspaces.find((w) => w.is_demo);
  const create = async () => {
    setBusy(true);
    try {
      const demo = await post<Workspace>("/demo");
      await reloadWorkspaces();
      selectWorkspace(demo.id);
      toast("Demo workspace created.");
    } catch (err) { toast(errorText(err, "The demo could not be created."), "error"); } finally { setBusy(false); }
  };
  const reset = async () => {
    setBusy(true);
    try {
      await del("/demo");
      await reloadWorkspaces();
      toast("Demo data removed.");
    } catch (err) { toast(errorText(err, "The demo could not be removed."), "error"); } finally { setBusy(false); }
  };
  return (
    <Card title="Demo mode">
      <p className="mb-3 text-[13px] text-text-2">Creates a separate, labelled workspace with generated surfaces and CC0 sample photos, analysed by the real pipeline. It never mixes with your other workspaces.</p>
      {existing ? <Button icon={Trash2} busy={busy} onClick={() => void reset()}>Remove demo data</Button> : <Button icon={FlaskConical} busy={busy} onClick={() => void create()}>Create demo workspace</Button>}
    </Card>
  );
}

function AssistantInfo() {
  const status = useApi<AssistantStatus>("/assistant/status");
  if (!status.data) return null;
  const s = status.data;
  return (
    <Card title="AI assistant">
      <p className="text-[13px] text-text-2">{s.message}</p>
      <p className="mt-1 text-xs text-text-3">
        {s.external_ai_enabled ? `Model ${s.model}. ${s.used_today} of ${s.daily_limit} external answers used in the last 24 hours. ` : ""}
        External AI is configured on the server through environment variables. API keys never reach the browser.
      </p>
    </Card>
  );
}

function DangerZone() {
  const { signOut } = useSession();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await post("/users/me/delete", { password });
      if (hasToken()) setToken(null);
      await signOut();
    } catch (err) { setError(errorText(err, "The account could not be deleted.")); }
  };
  return (
    <Card title="Delete account">
      <p className="mb-3 text-[13px] text-text-2">Permanently deletes your account, workspaces, images, results and reports.</p>
      <Button variant="danger" onClick={() => setOpen(true)}>Delete account</Button>
      {open && (
        <Modal title="Delete your account?" onClose={() => setOpen(false)}>
          <form onSubmit={submit} className="space-y-3">
            {error && <ErrorNote message={error} />}
            <p className="text-[13px] text-text-2">This cannot be undone. Enter your password to confirm.</p>
            <input aria-label="Password" type="password" autoComplete="current-password" className="field" required value={password} onChange={(e) => setPassword(e.target.value)} />
            <div className="flex justify-end gap-2"><Button onClick={() => setOpen(false)}>Cancel</Button><Button type="submit" variant="danger">Delete account</Button></div>
          </form>
        </Modal>
      )}
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-6">
      <PageHeader title="Settings" />
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <div className="space-y-4"><Profile /><PasswordForm /><DangerZone /></div>
        <div className="space-y-4"><Preferences /><Workspaces /><DemoMode /><AssistantInfo /></div>
      </div>
    </div>
  );
}

import { BarChart3, ChevronsUpDown, Cpu, FileText, GitCompare, History, LayoutDashboard, LogOut, Menu, Plus, ScanLine, Settings, ShieldCheck, TriangleAlert, X, type LucideIcon } from "lucide-react";
import { useState, type FormEvent } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Button, DemoBadge, Modal, useToast } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import { ApiError, post } from "../services/api";
import type { Workspace } from "../types";

const NAV: { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/inspections/new", label: "New Inspection", icon: ScanLine },
  { to: "/inspections", label: "Inspection History", icon: History },
  { to: "/comparison", label: "Image Comparison", icon: GitCompare },
  { to: "/defects", label: "Defect Analysis", icon: TriangleAlert },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/models", label: "Model Information", icon: Cpu },
  { to: "/settings", label: "Settings", icon: Settings },
];

function WorkspaceSwitcher() {
  const { workspaces, workspace, selectWorkspace, reloadWorkspaces } = useSession();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const toast = useToast();
  const create = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const created = await post<Workspace>("/workspaces", { name });
      await reloadWorkspaces();
      selectWorkspace(created.id);
      setCreating(false);
      setName("");
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "The workspace could not be created.", "error");
    }
  };
  return (
    <div className="relative">
      <button type="button" aria-expanded={open} aria-haspopup="listbox" onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-ink-700 bg-ink-850 px-2.5 py-2 text-left hover:border-ink-600">
        <span className="min-w-0">
          <span className="eyebrow block">Workspace</span>
          <span className="block truncate text-[13px] text-text-1">{workspace?.name ?? "Loading"}</span>
        </span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-text-3" />
      </button>
      {open && (
        <div className="absolute inset-x-0 top-full z-30 mt-1 rounded-md border border-ink-600 bg-ink-800 p-1 shadow-xl">
          {workspaces.map((w) => (
            <button key={w.id} type="button" onClick={() => { selectWorkspace(w.id); setOpen(false); }}
              className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-[13px] hover:bg-ink-700 ${w.id === workspace?.id ? "text-accent-strong" : "text-text-1"}`}>
              <span className="truncate">{w.name}</span>{w.is_demo && <DemoBadge />}
            </button>
          ))}
          <button type="button" onClick={() => { setCreating(true); setOpen(false); }} className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-[13px] text-text-2 hover:bg-ink-700">
            <Plus className="h-3.5 w-3.5" /> New workspace
          </button>
        </div>
      )}
      {creating && (
        <Modal title="New workspace" onClose={() => setCreating(false)}>
          <form onSubmit={create}>
            <label className="label" htmlFor="workspace-name">Name</label>
            <input id="workspace-name" className="field" required maxLength={80} value={name} autoFocus onChange={(e) => setName(e.target.value)} />
            <div className="mt-4 flex justify-end gap-2">
              <Button onClick={() => setCreating(false)}>Cancel</Button>
              <Button type="submit" variant="primary">Create</Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export function AppLayout() {
  const { user, signOut, workspace } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const system = useApi<{ storage_persistent: boolean; object_detection_available: boolean }>("/system/status");
  const isNew = pathname === "/inspections/new";
  const initials = (user?.full_name ?? "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="flex h-full">
      {menuOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMenuOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-ink-700 bg-ink-900 transition-transform lg:static lg:translate-x-0 ${menuOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-14 items-center gap-2 px-4">
          <ShieldCheck className="h-5 w-5 text-accent" />
          <span className="text-[15px] font-semibold">VisionGuard <span className="text-accent">AI</span></span>
          <button aria-label="Close menu" className="ml-auto p-1 text-text-3 lg:hidden" onClick={() => setMenuOpen(false)}><X className="h-4 w-4" /></button>
        </div>
        <div className="px-3 pb-3"><WorkspaceSwitcher /></div>
        <nav aria-label="Main" className="flex-1 space-y-0.5 overflow-y-auto px-3">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/" || to === "/inspections"} onClick={() => setMenuOpen(false)}
              className={({ isActive }) => {
                const active = isActive || (to === "/inspections" && pathname.startsWith("/inspections/") && !isNew);
                return `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors ${active ? "bg-ink-700 text-text-1" : "text-text-2 hover:bg-ink-800 hover:text-text-1"}`;
              }}>
              <Icon className="h-4 w-4 shrink-0" /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-2 border-t border-ink-700 p-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-700 text-xs font-semibold text-text-1" aria-hidden>{initials}</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] text-text-1">{user?.full_name}</div>
            <div className="truncate text-xs text-text-3">{user?.email}</div>
          </div>
          <button aria-label="Sign out" title="Sign out" onClick={() => void signOut()} className="rounded p-1.5 text-text-3 hover:bg-ink-800 hover:text-text-1"><LogOut className="h-4 w-4" /></button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 items-center gap-2 border-b border-ink-700 bg-ink-900 px-4 lg:hidden">
          <button aria-label="Open menu" onClick={() => setMenuOpen(true)} className="p-1 text-text-2"><Menu className="h-5 w-5" /></button>
          <span className="text-sm font-semibold">VisionGuard <span className="text-accent">AI</span></span>
        </div>
        {workspace?.is_demo && (
          <div role="note" className="border-b border-amber-400/30 bg-amber-400/10 px-4 py-1.5 text-xs text-amber-100">
            You are viewing a demo workspace. Its images are generated or CC0 samples, and it is kept apart from your real records. Remove it in Settings.
          </div>
        )}
        {system.data && !system.data.storage_persistent && (
          <div role="alert" className="border-b border-red-500/40 bg-red-500/10 px-4 py-1.5 text-xs text-red-100">
            This deployment has no persistent file storage. Uploaded images and reports can disappear when the server restarts. Do not use it for real inspections.
          </div>
        )}
        <main className="min-h-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>
    </div>
  );
}

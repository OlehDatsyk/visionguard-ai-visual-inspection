import { History as HistoryIcon, ScanLine, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthedImage, Button, Card, Empty, ErrorNote, PageHeader, Pagination, Spinner, StatusBadge } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import type { Category, Page, Project } from "../types";
import { formatDate, STATUS_LABELS } from "../utils/format";

export default function History() {
  const { workspace } = useSession();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(1);
  const categories = useApi<Category[]>("/categories");

  useEffect(() => {
    const timer = setTimeout(() => { setDebounced(query); setPage(1); }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const params = new URLSearchParams({ workspace_id: workspace?.id ?? "", page: String(page), page_size: "15" });
  if (debounced) params.set("q", debounced);
  if (status) params.set("status", status);
  if (category) params.set("category", category);
  const { data, error, loading, reload } = useApi<Page<Project>>(workspace ? `/projects?${params}` : null);
  const labels = Object.fromEntries((categories.data ?? []).map((c) => [c.key, c.label]));
  const filtered = Boolean(debounced || status || category);

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6">
      <PageHeader title="Inspection history" description="Open, search and filter your saved inspection projects."
        actions={<Button variant="primary" icon={ScanLine} onClick={() => navigate("/inspections/new")}>New inspection</Button>} />
      <Card bodyClass="">
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 p-3">
          <div className="relative min-w-52 flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-text-3" />
            <input aria-label="Search projects" className="field !pl-8" placeholder="Search by name or description" value={query} maxLength={120} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <select aria-label="Filter by status" className="field !w-auto" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select aria-label="Filter by category" className="field !w-auto" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
            <option value="">All categories</option>
            {categories.data?.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </div>
        {error && <div className="p-3"><ErrorNote message={error} onRetry={() => void reload()} /></div>}
        {loading && !data ? <Spinner /> : data && data.items.length === 0 ? (
          filtered ? <Empty icon={Search} title="No projects match these filters" />
            : <Empty icon={HistoryIcon} title="No inspection projects yet" action={<Button variant="primary" onClick={() => navigate("/inspections/new")}>Start an inspection</Button>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[13px]">
              <thead className="text-xs text-text-3">
                <tr>{["Project", "Category", "Status", "Images", "Objects", "Findings", "Not reviewed", "Updated"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-ink-700">
                {data?.items.map((p) => (
                  <tr key={p.id} className="hover:bg-ink-800">
                    <td className="max-w-72 px-4 py-2">
                      <Link to={`/inspections/${p.id}`} className="flex items-center gap-3">
                        <AuthedImage path={p.thumbnail_image_id ? `/images/${p.thumbnail_image_id}/file?variant=thumbnail` : null} alt="" className="h-9 w-12 shrink-0 rounded object-cover" fallback={<div className="h-9 w-12 shrink-0 rounded bg-ink-700" />} />
                        <span className="truncate text-text-1 hover:text-accent-strong">{p.name}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-text-2">{labels[p.category] ?? p.category}</td>
                    <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
                    <td className="data px-4 py-2 text-text-2">{p.image_count}</td>
                    <td className="data px-4 py-2 text-text-2">{p.object_count}</td>
                    <td className="data px-4 py-2 text-text-2">{p.finding_count}</td>
                    <td className="data px-4 py-2 text-text-2">{p.unreviewed_count}</td>
                    <td className="whitespace-nowrap px-4 py-2 text-text-3">{formatDate(p.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />}
      </Card>
    </div>
  );
}

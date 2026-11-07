import { ExternalLink, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { FindingDetail } from "../components/FindingPanel";
import { AuthedImage, BandBadge, Card, Empty, ErrorNote, Modal, PageHeader, Pagination, ReviewBadge, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import type { Finding, Page } from "../types";
import { BAND_LABELS, CATEGORY_LABELS, categoryLabel, formatDate, REVIEW_LABELS } from "../utils/format";

export default function DefectAnalysis() {
  const { workspace } = useSession();
  const [category, setCategory] = useState("");
  const [review, setReview] = useState("");
  const [band, setBand] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Finding | null>(null);
  const params = new URLSearchParams({ workspace_id: workspace?.id ?? "", page: String(page) });
  if (category) params.set("category", category);
  if (review) params.set("review_status", review);
  if (band) params.set("band", band);
  const { data, error, loading, reload } = useApi<Page<Finding>>(workspace ? `/findings?${params}` : null);
  const reset = (setter: (value: string) => void) => (value: string) => { setter(value); setPage(1); };
  const filtered = Boolean(category || review || band);

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6">
      <PageHeader title="Defect analysis" description="Every finding across this workspace. Findings come from image-processing heuristics and stay unverified until a person reviews them." />
      <Card bodyClass="">
        <div className="flex flex-wrap gap-2 border-b border-ink-700 p-3">
          <select aria-label="Filter by category" className="field !w-auto" value={category} onChange={(e) => reset(setCategory)(e.target.value)}>
            <option value="">All categories</option>{Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select aria-label="Filter by review status" className="field !w-auto" value={review} onChange={(e) => reset(setReview)(e.target.value)}>
            <option value="">All review states</option>{Object.entries(REVIEW_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select aria-label="Filter by confidence band" className="field !w-auto" value={band} onChange={(e) => reset(setBand)(e.target.value)}>
            <option value="">All bands</option>{Object.entries(BAND_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        {error && <div className="p-3"><ErrorNote message={error} onRetry={() => void reload()} /></div>}
        {loading && !data ? <Spinner /> : data?.items.length === 0 ? (
          <Empty icon={TriangleAlert} title={filtered ? "No findings match these filters" : "No findings yet"}>
            {filtered ? undefined : "Findings appear here after an inspection is analysed."}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-[13px]">
              <thead className="text-xs text-text-3"><tr>{["Finding", "Image", "Score", "Band", "Review", "Found"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-ink-700">
                {data?.items.map((f) => (
                  <tr key={f.id} tabIndex={0} className="cursor-pointer hover:bg-ink-800" onClick={() => setOpen(f)} onKeyDown={(e) => { if (e.key === "Enter") setOpen(f); }}>
                    <td className="px-4 py-2"><div className="text-text-1">{categoryLabel(f.category)}</div><div className="data text-xs text-text-3">{f.code}</div></td>
                    <td className="max-w-64 px-4 py-2"><div className="flex items-center gap-2">
                      <AuthedImage path={`/images/${f.image_id}/file?variant=thumbnail`} alt="" className="h-9 w-12 shrink-0 rounded object-cover" />
                      <div className="min-w-0"><div className="truncate text-text-2">{f.image_filename}</div><div className="truncate text-xs text-text-3">{f.project_name}</div></div>
                    </div></td>
                    <td className="data px-4 py-2 text-text-2">{f.score_type === "image_quality" ? "None" : f.score.toFixed(2)}</td>
                    <td className="px-4 py-2"><BandBadge band={f.confidence_band} /></td>
                    <td className="px-4 py-2"><ReviewBadge status={f.review_status} /></td>
                    <td className="whitespace-nowrap px-4 py-2 text-text-3">{formatDate(f.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />}
      </Card>
      {open && (
        <Modal title={`Finding ${open.code}`} onClose={() => setOpen(null)}>
          <FindingDetail finding={open} onChange={(updated) => { setOpen({ ...open, ...updated }); void reload(); }} />
          {open.project_id && <Link to={`/inspections/${open.project_id}`} className="mt-3 inline-flex items-center gap-1 text-xs text-accent hover:underline"><ExternalLink className="h-3 w-3" />Open in inspection workspace</Link>}
        </Modal>
      )}
    </div>
  );
}

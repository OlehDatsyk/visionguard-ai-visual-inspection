import { FileText, FlaskConical, Images, ScanLine, TriangleAlert, ClipboardCheck, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { RankedBars, ChartCard, TrendChart } from "../components/charts";
import { AuthedImage, Button, Card, Empty, ErrorNote, PageHeader, Spinner, StatusBadge, useToast } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import { ApiError, post } from "../services/api";
import type { Overview as OverviewData, Workspace } from "../types";
import { categoryLabel, formatDate } from "../utils/format";

function Stat({ icon: Icon, label, value, hint }: { icon: LucideIcon; label: string; value: number; hint?: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between text-text-3"><span className="text-xs">{label}</span><Icon className="h-4 w-4" /></div>
      <div className="data mt-1.5 text-2xl font-semibold text-text-1">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-text-3">{hint}</div>}
    </div>
  );
}

const shortDate = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export default function Overview() {
  const { workspace, reloadWorkspaces, selectWorkspace } = useSession();
  const { data, error, loading, reload } = useApi<OverviewData>(workspace ? `/analytics/overview?workspace_id=${workspace.id}` : null);
  const [seeding, setSeeding] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const loadDemo = async () => {
    setSeeding(true);
    try {
      const demo = await post<Workspace>("/demo");
      await reloadWorkspaces();
      selectWorkspace(demo.id);
      toast("Demo workspace created.");
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "The demo could not be created.", "error");
    } finally {
      setSeeding(false);
    }
  };

  if (loading && !data) return <Spinner />;
  if (error) return <div className="p-6"><ErrorNote message={error} onRetry={() => void reload()} /></div>;
  if (!data) return null;
  const isEmpty = data.totals.inspections === 0;

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6">
      <PageHeader title="Overview" description={`Figures from the records in ${workspace?.name}.`}
        actions={<Button variant="primary" icon={ScanLine} onClick={() => navigate("/inspections/new")}>New inspection</Button>} />
      {isEmpty ? (
        <Card>
          <Empty icon={ScanLine} title="No inspections yet" action={<>
            <Button variant="primary" icon={ScanLine} onClick={() => navigate("/inspections/new")}>Start an inspection</Button>
            {!workspace?.is_demo && <Button icon={FlaskConical} busy={seeding} onClick={() => void loadDemo()}>Explore demo data</Button>}
          </>}>
            Upload images to detect objects and flag potential defects for review. Demo mode creates a separate, clearly labelled workspace analysed by the same pipeline.
          </Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat icon={ScanLine} label="Total inspections" value={data.totals.inspections} />
            <Stat icon={Images} label="Images analysed" value={data.totals.images_analysed} />
            <Stat icon={TriangleAlert} label="Potential defects" value={data.totals.potential_defects} hint="Excludes reviewed false positives" />
            <Stat icon={ClipboardCheck} label="Inspections requiring review" value={data.totals.requiring_review} />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <ChartCard title="Inspections created, last 30 days" height={200}
                table={{ head: ["Date", "Inspections"], rows: data.inspection_trend.filter((d) => d.count > 0).map((d) => [d.date, d.count]) }}>
                <TrendChart data={data.inspection_trend} xKey="date" tickFormatter={shortDate} />
              </ChartCard>
            </div>
            <ChartCard title="Potential defects by category" height={200}
              table={{ head: ["Category", "Findings"], rows: data.defect_distribution.map((d) => [categoryLabel(d.category), d.count]) }}>
              {data.defect_distribution.length
                ? <RankedBars data={data.defect_distribution} labelKey="category" name="Findings" formatLabel={categoryLabel} />
                : <p className="pt-16 text-center text-sm text-text-3">No potential defects recorded.</p>}
            </ChartCard>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Recent inspections" className="lg:col-span-2" bodyClass="" actions={<Link className="text-xs text-accent hover:underline" to="/inspections">View all</Link>}>
              <ul className="divide-y divide-ink-700">
                {data.recent_projects.map((p) => (
                  <li key={p.id}>
                    <Link to={`/inspections/${p.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-ink-800">
                      <AuthedImage path={p.thumbnail_image_id ? `/images/${p.thumbnail_image_id}/file?variant=thumbnail` : null} alt="" className="h-10 w-14 shrink-0 rounded object-cover" fallback={<div className="h-10 w-14 shrink-0 rounded bg-ink-700" />} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] text-text-1">{p.name}</div>
                        <div className="text-xs text-text-3">{p.image_count} image{p.image_count === 1 ? "" : "s"}, {p.finding_count} finding{p.finding_count === 1 ? "" : "s"}, updated {formatDate(p.updated_at)}</div>
                      </div>
                      <StatusBadge status={p.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
            <div className="space-y-4">
              <Card title="Recent reports" bodyClass="">
                {data.recent_reports.length === 0 ? <p className="p-4 text-sm text-text-3">No reports generated yet.</p> : (
                  <ul className="divide-y divide-ink-700">
                    {data.recent_reports.map((r) => (
                      <li key={r.id}><Link to="/reports" className="flex items-center gap-2 px-4 py-2 hover:bg-ink-800">
                        <FileText className="h-4 w-4 shrink-0 text-text-3" />
                        <span className="min-w-0"><span className="block truncate text-[13px] text-text-1">{r.title}</span><span className="text-xs text-text-3">{formatDate(r.created_at)}</span></span>
                      </Link></li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title="Frequent inspection categories" bodyClass="">
                <ul className="divide-y divide-ink-700">
                  {data.frequent_categories.map((c) => (
                    <li key={c.category} className="flex items-center justify-between gap-2 px-4 py-2 text-[13px]"><span className="truncate text-text-2">{c.label}</span><span className="data text-text-1">{c.count}</span></li>
                  ))}
                </ul>
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

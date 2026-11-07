import { BarChart3 } from "lucide-react";
import { useState } from "react";
import { ChartCard, RankedBars, StackedReview, TrendChart } from "../components/charts";
import { Card, Empty, ErrorNote, PageHeader, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useSession } from "../hooks/useSession";
import type { Insights } from "../types";
import { categoryLabel, REVIEW_LABELS, STATUS_LABELS } from "../utils/format";

const weekLabel = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-text-3">{label}</div>
      <div className="data mt-1 text-2xl font-semibold text-text-1">{value}</div>
      <div className="mt-0.5 text-[11px] text-text-3">{hint}</div>
    </div>
  );
}

export default function Analytics() {
  const { workspace } = useSession();
  const [days, setDays] = useState(90);
  const { data, error, loading, reload } = useApi<Insights>(workspace ? `/analytics/insights?workspace_id=${workspace.id}&days=${days}` : null);

  if (loading && !data) return <Spinner />;
  if (error) return <div className="p-6"><ErrorNote message={error} onRetry={() => void reload()} /></div>;
  if (!data) return null;
  const fp = data.false_positive;
  const hasData = data.status_distribution.length > 0;
  const stacked = fp.by_category.map((c) => ({ category: c.category, confirmed: c.confirmed, false_positive: c.false_positive, unconfirmed: c.total - c.confirmed - c.false_positive }));

  return (
    <div className="mx-auto max-w-7xl p-4 sm:p-6">
      <PageHeader title="Analytics" description="Built from this workspace's records and your review decisions."
        actions={
          <select aria-label="Time range" className="field !w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={365}>Last 12 months</option>
          </select>
        } />
      {!hasData ? <Card><Empty icon={BarChart3} title="No inspection records yet">Charts appear after your first inspection.</Empty></Card> : (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Tile label="False-positive rate" value={fp.rate === null ? "No decisions yet" : `${(fp.rate * 100).toFixed(0)}%`}
              hint={fp.rate === null ? "Review findings to calculate this" : `${fp.false_positive} of ${fp.decided} decided findings, from your reviews`} />
            <Tile label="Confirmed or resolved" value={String(fp.confirmed)} hint="Findings a person accepted as real" />
            <Tile label="Awaiting a decision" value={String(fp.unconfirmed)} hint="Unreviewed or marked as needing review" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Inspections over time, by week" table={{ head: ["Week starting", "Inspections"], rows: data.inspections_over_time.filter((d) => d.count).map((d) => [d.week_start, d.count]) }}>
              <TrendChart data={data.inspections_over_time} xKey="week_start" tickFormatter={weekLabel} />
            </ChartCard>
            <ChartCard title="Findings by category" table={{ head: ["Category", "Findings"], rows: data.findings_by_category.map((d) => [categoryLabel(d.category), d.count]) }}>
              {data.findings_by_category.length ? <RankedBars data={data.findings_by_category} labelKey="category" name="Findings" formatLabel={categoryLabel} /> : <p className="pt-20 text-center text-sm text-text-3">No potential defects recorded.</p>}
            </ChartCard>
            <ChartCard title="Review outcomes by category" note="Decisions by reviewers. This describes your reviews, not model accuracy."
              table={{ head: ["Category", "Confirmed or resolved", "False positive", "No decision yet"], rows: stacked.map((c) => [categoryLabel(c.category), c.confirmed, c.false_positive, c.unconfirmed]) }}>
              {stacked.length ? <StackedReview data={stacked} formatLabel={categoryLabel} /> : <p className="pt-20 text-center text-sm text-text-3">No potential defects recorded.</p>}
            </ChartCard>
            <ChartCard title="Inspection status" table={{ head: ["Status", "Inspections"], rows: data.status_distribution.map((s) => [STATUS_LABELS[s.status], s.count]) }}>
              <RankedBars data={data.status_distribution.map((s) => ({ status: STATUS_LABELS[s.status], count: s.count }))} labelKey="status" name="Inspections" />
            </ChartCard>
            <ChartCard title="Most frequently detected objects" table={{ head: ["Object", "Detections"], rows: data.top_objects.map((o) => [o.label, o.count]) }}>
              {data.top_objects.length ? <RankedBars data={data.top_objects} labelKey="label" name="Detections" /> : <p className="pt-20 text-center text-sm text-text-3">No objects detected yet.</p>}
            </ChartCard>
            <Card title="Review state of all potential defects" bodyClass="">
              <table className="w-full text-[13px]"><tbody className="divide-y divide-ink-700">
                {data.review_outcomes.length === 0 && <tr><td className="p-4 text-text-3">No potential defects recorded.</td></tr>}
                {data.review_outcomes.map((r) => <tr key={r.status}><td className="px-4 py-2 text-text-2">{REVIEW_LABELS[r.status]}</td><td className="data px-4 py-2 text-right text-text-1">{r.count}</td></tr>)}
                <tr><td className="px-4 py-2 text-text-3">Review decisions recorded in total</td><td className="data px-4 py-2 text-right text-text-1">{data.review_decisions_recorded}</td></tr>
              </tbody></table>
            </Card>
          </div>
          <p className="text-xs text-text-3">Accuracy, precision and recall are not shown, because no labelled ground-truth data exists. Confidence scores are not model accuracy.</p>
        </div>
      )}
    </div>
  );
}

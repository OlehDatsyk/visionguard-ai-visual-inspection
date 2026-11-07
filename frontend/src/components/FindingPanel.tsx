import { AlertTriangle, CheckCircle2, Eye, XCircle, type LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, patch } from "../services/api";
import type { Finding, ReviewStatus } from "../types";
import { categoryLabel, formatDateTime, pretty, REVIEW_LABELS, scoreName } from "../utils/format";
import { BandBadge, Button, ReviewBadge, useToast } from "./ui";

const ACTIONS: { value: Exclude<ReviewStatus, "unreviewed">; icon: LucideIcon }[] = [
  { value: "confirmed", icon: AlertTriangle },
  { value: "false_positive", icon: XCircle },
  { value: "needs_review", icon: Eye },
  { value: "resolved", icon: CheckCircle2 },
];

/** Details of one finding, with the controls that record a person's decision. */
export function FindingDetail({ finding, onChange }: { finding: Finding; onChange: (updated: Finding) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [history, setHistory] = useState<Finding["reviews"]>([]);
  const toast = useToast();

  useEffect(() => {
    setNote("");
    let cancelled = false;
    api<Finding>(`/findings/${finding.id}`).then((f) => { if (!cancelled) setHistory(f.reviews ?? []); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [finding.id]);

  const decide = async (decision: ReviewStatus) => {
    setBusy(decision);
    try {
      const updated = await patch<Finding>(`/findings/${finding.id}/review`, { decision, note });
      setHistory(updated.reviews ?? []);
      setNote("");
      onChange(updated);
      toast(`Recorded as ${REVIEW_LABELS[decision].toLowerCase()}.`);
    } catch (err) {
      toast(err instanceof ApiError ? err.message : "The decision could not be saved.", "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-medium text-text-1">{categoryLabel(finding.category)}</span>
          <span className="data text-xs text-text-3">{finding.code}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-1.5"><BandBadge band={finding.confidence_band} /><ReviewBadge status={finding.review_status} /></div>
      </div>
      <p className="text-[13px] leading-relaxed text-text-2">{finding.explanation}</p>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <dt className="text-text-3">{scoreName(finding.score_type)}</dt>
        <dd className="data text-right text-text-1">{finding.score_type === "image_quality" ? "None" : finding.score.toFixed(2)}</dd>
        <dt className="text-text-3">Location (x, y, w, h)</dt>
        <dd className="data text-right text-text-1">{[finding.x, finding.y, finding.width, finding.height].map((v) => Math.round(v)).join(", ")}</dd>
        {Object.entries(finding.metrics).map(([key, value]) => (
          <div key={key} className="contents"><dt className="text-text-3">{pretty(key)}</dt><dd className="data text-right text-text-1">{value}</dd></div>
        ))}
      </dl>
      <p className="text-xs text-text-3"><span className="text-text-2">Method:</span> {finding.method}. Scores are uncalibrated and are not a probability of being correct.</p>
      <div className="border-t border-ink-700 pt-3">
        <label className="label" htmlFor={`note-${finding.id}`}>Review note (optional)</label>
        <textarea id={`note-${finding.id}`} className="field text-xs" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          {ACTIONS.map(({ value, icon }) => (
            <Button key={value} small icon={icon} busy={busy === value} disabled={busy !== null} variant={finding.review_status === value ? "primary" : "secondary"} onClick={() => void decide(value)}>
              {REVIEW_LABELS[value]}
            </Button>
          ))}
        </div>
      </div>
      {history && history.length > 0 && (
        <div>
          <p className="eyebrow mb-1">Decision history</p>
          <ul className="space-y-1 text-xs text-text-3">
            {[...history].reverse().map((r) => (
              <li key={r.id}><span className="text-text-2">{REVIEW_LABELS[r.decision]}</span>, {formatDateTime(r.created_at)}{r.note ? `: ${r.note}` : ""}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

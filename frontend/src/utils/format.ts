import type { Band, ProjectStatus, ReviewStatus } from "../types";

export const pretty = (value: string): string => {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};
export const formatDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
export const formatDateTime = (iso: string): string =>
  new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
export const formatBytes = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

export const CATEGORY_LABELS: Record<string, string> = {
  crack_like: "Crack-like",
  scratch_like: "Scratch-like",
  surface_anomaly: "Surface anomaly",
  discolouration: "Discolouration",
  corrosion_like: "Corrosion-like",
  manual_inspection: "Manual inspection area",
};
export const categoryLabel = (key: string): string => CATEGORY_LABELS[key] ?? pretty(key);

export const BAND_LABELS: Record<Band, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
  unverified: "Unverified",
};
export const REVIEW_LABELS: Record<ReviewStatus, string> = {
  unreviewed: "Not reviewed",
  confirmed: "Confirmed",
  false_positive: "False positive",
  needs_review: "Needs review",
  resolved: "Resolved",
};
export const STATUS_LABELS: Record<ProjectStatus, string> = {
  draft: "Draft",
  processing: "Processing",
  completed: "Completed",
  requires_review: "Requires review",
  archived: "Archived",
};
export const scoreName = (scoreType: string): string =>
  scoreType === "model_confidence" ? "Model confidence" : scoreType === "heuristic_anomaly" ? "Anomaly score" : "No score";

export interface User { id: string; email: string; full_name: string; created_at: string }
export interface TokenResponse { access_token: string; expires_in: number; user: User }
export interface Workspace { id: string; name: string; is_demo: boolean; created_at: string }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number }
export type ProjectStatus = "draft" | "processing" | "completed" | "requires_review" | "archived";
export type ReviewStatus = "unreviewed" | "confirmed" | "false_positive" | "needs_review" | "resolved";
export type Band = "high" | "medium" | "low" | "unverified";

export interface Project {
  id: string; workspace_id: string; name: string; description: string; category: string; status: ProjectStatus;
  notes: string; created_at: string; updated_at: string; image_count: number; finding_count: number;
  unreviewed_count: number; object_count: number; thumbnail_image_id: string | null;
}
export interface Category { key: string; label: string; checks: string[]; not_assessed: { check: string; reason: string }[] }
export interface ImageMeta {
  file_format: string; file_size: number; width: number; height: number; display_width: number; display_height: number;
  checksum_sha256: string; had_exif: boolean; had_gps: boolean; quality: Record<string, unknown>;
}
export interface InspectionImage {
  id: string; project_id: string | null; filename: string; description: string; status: string;
  analysis_notes: string[]; unsupported_checks: { check: string; reason: string }[]; analysed_at: string | null;
  created_at: string; has_processed: boolean; metadata: ImageMeta;
}
export interface UploadResult { accepted: InspectionImage[]; rejected: { filename: string; reason: string }[] }
export interface DetectedObject {
  id: string; image_id: string; label: string; confidence: number; confidence_band: Band; x: number; y: number;
  width: number; height: number; polygon: number[][] | null; segmentation_method: string | null; model_name: string;
}
export interface Review { id: string; decision: ReviewStatus; note: string; created_at: string }
export interface Finding {
  id: string; image_id: string; code: string; category: string; finding_type: "potential_defect" | "manual_inspection";
  score: number; score_type: string; confidence_band: Band; x: number; y: number; width: number; height: number;
  polygon: number[][] | null; method: string; explanation: string; metrics: Record<string, number>;
  review_status: ReviewStatus; created_at: string; updated_at: string; project_id: string | null;
  project_name: string | null; image_filename: string | null; reviews?: Review[];
}
export interface ImageResults { image: InspectionImage; objects: DetectedObject[]; findings: Finding[] }
export interface Job {
  id: string; job_type: string; status: "queued" | "running" | "completed" | "failed"; project_id: string | null;
  comparison_id: string | null; items_total: number; items_done: number; stage: string; attempts: number;
  max_attempts: number; error_message: string | null; queued_at: string; started_at: string | null; finished_at: string | null;
}
export interface ComparisonMetrics {
  ssim: number; changed_area_pct: number; mean_absolute_difference: number; edge_difference_pct: number;
  feature_inlier_ratio: number; brightness_shift: number; alignment_status: string; feature_matches: number;
  feature_inliers: number; overlap_pct: number; difference_threshold: number;
}
export interface Region { x: number; y: number; width: number; height: number; area_pct: number }
export interface Comparison {
  id: string; workspace_id: string; project_id: string | null; name: string; status: string;
  metrics: ComparisonMetrics; regions: Region[]; warnings: string[]; width: number; height: number;
  before_filename: string; after_filename: string; created_at: string;
  metric_explanations: Record<string, string>; limitations: string[]; job: Job | null;
}
export interface Report {
  id: string; project_id: string; project_name: string; title: string; final_notes: string; file_size: number;
  page_count: number; created_at: string;
}
export interface Overview {
  totals: { inspections: number; images_analysed: number; potential_defects: number; requiring_review: number };
  recent_projects: Project[];
  defect_distribution: { category: string; count: number }[];
  inspection_trend: { date: string; count: number }[];
  frequent_categories: { category: string; label: string; count: number }[];
  recent_reports: { id: string; title: string; project_name: string; created_at: string }[];
}
export interface Insights {
  window_days: number;
  inspections_over_time: { week_start: string; count: number }[];
  findings_by_category: { category: string; count: number }[];
  review_outcomes: { status: ReviewStatus; count: number }[];
  false_positive: {
    confirmed: number; false_positive: number; decided: number; unconfirmed: number; rate: number | null;
    by_category: { category: string; confirmed: number; false_positive: number; total: number; rate: number | null }[];
  };
  status_distribution: { status: ProjectStatus; count: number }[];
  top_objects: { label: string; count: number }[];
  review_decisions_recorded: number;
}
export interface DetectorInfo {
  key: string; name: string; type: string; version: string; licence: string; source: string; available: boolean;
  unavailable_reason: string | null; input_requirements: string; processing: string; supported_categories: string[];
  limitations: string[]; confidence_threshold: number;
}
export interface ModuleInfo {
  key: string; name: string; reports: string[]; technique: string; available: boolean; type: string; licence: string; limitations: string[];
}
export interface ModelsResponse {
  object_detectors: DetectorInfo[]; image_processing_modules: ModuleInfo[];
  segmentation: { name: string; type: string; available: boolean; limitations: string[] };
  performance_statistics: null; performance_note: string;
}
export interface AssistantStatus { provider: string; external_ai_enabled: boolean; model: string | null; daily_limit: number; used_today: number; message: string }
export interface ChatMessage { id: string; role: "user" | "assistant"; content: string; source: string; created_at: string }
export interface Conversation { id: string; project_id: string | null; comparison_id: string | null; title: string; created_at: string; messages: ChatMessage[] }
export interface UserSettings { default_category: string | null; detector_confidence_threshold: number; overlay_opacity: number }

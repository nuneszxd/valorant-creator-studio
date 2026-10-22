export type JobState = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: number;
  kind: string;
  label: string;
  state: JobState;
  state_label: string;
  recording_id: number | null;
  clip_id: number | null;
  progress: number | null;
  progress_label: string | null;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobsSummary {
  counts: Record<string, number>;
  active: Job[];
  labels: Record<string, string>;
}

export interface Recording {
  id: number;
  name: string;
  path: string;
  source: string;
  source_ref: string | null;
  source_meta: Record<string, unknown> | null;
  size_bytes: number | null;
  duration_s: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  audio_streams: number;
  game: string;
  map: string | null;
  agent: string | null;
  notes: string | null;
  status: string;
  last_error: string | null;
  imported_at: string;
  recorded_at: string | null;
  file_exists: boolean;
  browser_playable: boolean;
  candidates_count?: number;
  approved_count?: number;
  clips_count?: number;
  warnings?: string[];
}

export interface Analysis {
  id: number;
  recording_id: number;
  level: string;
  status: string;
  stats: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface RecordingDetail extends Recording {
  latest_analysis: Analysis | null;
  transcript_segments: number;
}

export interface Reason {
  key: string;
  label: string;
  value: number | null;
  weight: number;
  points: number;
  detail: string;
}

export interface Candidate {
  id: number;
  recording_id: number;
  start_s: number;
  end_s: number;
  duration_s: number;
  title: string;
  moment_type: string;
  type_label: string;
  score: number;
  confidence: string;
  reasons: Reason[] | null;
  excerpt: string | null;
  status: "pending" | "approved" | "rejected";
  status_label: string;
  outcome: "good" | "bad" | null;
  outcome_label: string | null;
  tags: string[] | null;
  manual: boolean;
  recording_name?: string;
  recording_map?: string | null;
  recording_agent?: string | null;
  clip_id?: number | null;
}

export interface TranscriptSegment {
  id: number;
  start_s: number;
  end_s: number;
  text: string;
}

export interface CandidateDetail extends Candidate {
  recording: { id: number; name: string; duration_s: number | null; map: string | null; agent: string | null; width: number | null; height: number | null };
  transcript: TranscriptSegment[];
}

export interface Signals {
  analysis_id: number | null;
  window_s: number | null;
  rms_db: number[];
  scenes: Array<[number, number]>;
  p50: number | null;
  p95: number | null;
}

export interface CropRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface RenderConfig {
  width: number;
  height: number;
  layout: "blur" | "solid" | "fill";
  background_color: string;
  focus_x: number;
  crop: CropRegion | null;
  encoder: "libx264" | "h264_amf" | "h264_nvenc" | "h264_qsv";
  preset: string;
  crf: number;
  bitrate_kbps: number;
  fps: number | null;
  audio_bitrate_kbps: number;
  volume_db: number;
  loudnorm: boolean;
  fade_s: number;
  subtitles: boolean;
}

export interface SubtitleStyle {
  font: string;
  size_pct: number;
  text_color: string;
  highlight_color: string;
  outline_color: string;
  outline_px: number;
  bold: boolean;
  uppercase: boolean;
  position_pct: number;
  max_words_per_line: number;
  max_chars_per_line: number;
  highlight_words: boolean;
}

export interface CueWord {
  start: number;
  end: number;
  text: string;
}

export interface Cue {
  start: number;
  end: number;
  text: string;
  words?: CueWord[] | null;
}

export interface CopyPack {
  hooks: string[];
  titles: string[];
  caption: string;
  hashtags: string[];
  description: string;
  cover_text: string[];
  comment_cta: string;
  notes?: string[];
  generated_at?: string;
  source?: string;
  edited?: boolean;
}

export interface Clip {
  id: number;
  candidate_id: number | null;
  recording_id: number;
  title: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  moment_type: string;
  type_label: string;
  map: string | null;
  agent: string | null;
  facts: Record<string, string> | null;
  render_config: RenderConfig | null;
  subtitles: Cue[] | null;
  subtitle_style: SubtitleStyle | null;
  status: "draft" | "rendering" | "ready";
  status_label: string;
  output_path: string | null;
  output_size: number | null;
  rendered_at: string | null;
  last_error: string | null;
  preview_path: string | null;
  copy_pack: CopyPack | null;
  has_output: boolean;
  has_preview: boolean;
  recording_name?: string;
  score?: number | null;
  created_at: string;
}

export interface ClipDetail extends Clip {
  recording: { id: number; name: string; duration_s: number | null; width: number | null; height: number | null; map: string | null; agent: string | null; audio_streams: number; video_codec: string | null; audio_codec: string | null };
  candidate: { id: number; score: number; confidence: string; excerpt: string | null } | null;
  active_jobs: Job[];
}

export interface RenderPlan {
  mode: string;
  output_size: string;
  duration_s: number;
  command: string[];
  filter_graph: string;
  notes: string[];
  subtitles_applied: boolean;
}

export interface Publication {
  id: number;
  clip_id: number | null;
  platform: string;
  url: string | null;
  status: "planned" | "published";
  status_label: string;
  planned_for: string | null;
  published_at: string | null;
  format: string | null;
  theme: string | null;
  hook: string | null;
  duration_s: number | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  avg_watch_s: number | null;
  retention_pct: number | null;
  notes: string | null;
  feedback: "good" | "bad" | null;
  metrics_updated_at: string | null;
}

export interface ReportGroup {
  group: string;
  n: number;
  median_views: number | null;
  median_engagement_rate: number | null;
  median_avg_watch_s: number | null;
  vs_overall_median: number | null;
  best_example: { id: number; url: string | null; views: number; hook: string | null };
  warnings: string[];
}

export interface Report {
  group_by: string;
  overall: { published: number; with_views: number; median_views: number | null; median_engagement_rate: number | null };
  groups: ReportGroup[];
  reading_note: string;
  min_sample: number;
}

export interface IdeaReason {
  kind: string;
  evidence: string;
  text: string;
}

export interface IdeaSuggestion {
  format: string;
  title: string;
  priority: number;
  reasons: IdeaReason[];
  next_step: string;
  priority_note: string;
}

export interface ScriptBeat {
  beat: string;
  guide: string;
  your_text: string;
}

export interface Idea {
  id: number;
  title: string;
  format: string | null;
  status: string;
  status_label: string;
  rationale: IdeaReason[] | null;
  script: { title: string; target_duration: string; beats: ScriptBeat[]; checklist: string[] } | null;
  source: string;
}

export interface TrendObserved {
  observed: Record<string, unknown>;
  estimated: Record<string, unknown>;
  hypotheses: string[];
}

export interface Trend {
  id: number;
  run_id: number;
  kind: string;
  label: string;
  source: string;
  source_url: string | null;
  collected_at: string;
  observed: TrendObserved;
  evidence: string;
  relevance: string | null;
  suggestion: string | null;
  confidence: string;
  limitations: string | null;
  sample_size: number;
}

export interface RadarRun {
  id: number;
  source: string;
  status: string;
  collected_at: string;
  finished_at: string | null;
  sample_size: number;
  error: string | null;
  trends_count?: number;
  params: Record<string, unknown> | null;
  quota: Record<string, unknown> | null;
}

export interface RadarStatus {
  youtube: { configured: boolean; quota: { day: string; search_calls_used: number; search_calls_limit: number; search_calls_remaining: number } };
  twitch: { configured: boolean };
  manual_items: number;
  last_runs: Record<string, RadarRun | null>;
  sources: Record<string, string>;
  limitations: string[];
}

export interface ManualItem {
  id: number;
  platform: string;
  url: string | null;
  title: string | null;
  views: number | null;
  likes: number | null;
  comments: number | null;
  duration_s: number | null;
  hashtags: string[] | null;
  observed_at: string;
  notes: string | null;
  extra: Record<string, string | null> | null;
}

export interface TwitchResolve {
  kind: string;
  metadata_available: boolean;
  can_download_via_api: boolean;
  retention_note: string;
  download_steps: string[];
  messages: string[];
  video: { id: string; title: string; user_name: string; created_at: string; duration_s: number | null; type: string; view_count: number | null; url: string } | null;
  live: { login: string; is_live: boolean; title: string | null } | null;
}

export interface AnalysisLevelInfo {
  label: string;
  description: string;
  scenes: boolean;
  transcription: "off" | "candidates" | "full";
  model: string | null;
  warnings: string[];
}

export interface AnalysisLevels {
  levels: Record<string, AnalysisLevelInfo>;
  models: Record<string, { approx_download: string; note: string }>;
  provider: string;
  provider_ready: boolean;
  provider_message: string;
}

export interface Capabilities {
  app_version: string;
  platform: string;
  python: string;
  ffmpeg: {
    available: boolean;
    ffmpeg_path: string | null;
    version: string | null;
    encoders: Record<string, boolean>;
    filters: Record<string, boolean>;
  };
  transcription: { faster_whisper_installed: boolean; whisper_cpp_configured: boolean; provider: string; note: string };
  integrations: { twitch: boolean; youtube: boolean };
  paths: { data_dir: string; output_dir: string };
}

export interface AppSettings {
  output_dir: string | null;
  transcription_provider: "faster-whisper" | "whisper.cpp";
  whisper_model: "tiny" | "base" | "small" | "medium";
  whisper_language: string;
  whisper_beam_size: number;
  whisper_cpp_path: string | null;
  whisper_cpp_model_path: string | null;
  analysis: {
    max_candidates: number;
    min_intensity: number;
    pre_roll_s: number;
    post_roll_s: number;
    min_separation_s: number;
    scene_threshold: number;
    audio_window_s: number;
    audio_stream_index: number;
  };
  scoring_weights: Record<string, number>;
  keywords: Record<string, string[]>;
  reaction_keywords: string[];
  render: RenderConfig;
  subtitle_style: SubtitleStyle;
  base_hashtags: string[];
  youtube_search_daily_limit: number;
}

export interface SettingsResponse {
  settings: AppSettings;
  defaults: AppSettings;
  effective_output_dir: string;
  data_dir: string;
  integrations: { twitch: boolean; youtube: boolean };
}

export interface CreatorProfile {
  channel_name: string;
  links: { twitch: string; tiktok: string; youtube: string; instagram: string; other: string[] };
  rank_current: string;
  rank_target: string;
  agents: string[];
  content_style: string[];
  publishing_frequency_per_week: number | null;
  target_audience: string;
  formats_to_try: string[];
  preferred_types: string[];
  editing_preferences: string;
  preferred_duration_min_s: number;
  preferred_duration_max_s: number;
  series_name: string;
  past_results_notes: string;
}

export interface Overview {
  recordings: { total: number; by_status: Record<string, number> };
  candidates: { total: number; by_status: Record<string, number> };
  clips: { total: number; by_status: Record<string, number> };
  publications: { total: number; published: number; planned: number };
  ideas: number;
  jobs: { counts: Record<string, number>; recent: Job[]; labels: Record<string, string> };
  recent_recordings: Recording[];
  top_pending_candidates: Array<{ id: number; title: string; score: number; confidence: string; moment_type: string; start_s: number; end_s: number; recording_name: string }>;
  radar: Record<string, { id: number; collected_at: string; sample_size: number } | null>;
  disk: { exports_bytes: number; previews_bytes: number };
  setup: { ffmpeg: boolean; profile_filled: boolean; has_recording: boolean; integrations: { twitch: boolean; youtube: boolean } };
}

export interface Facets {
  games: string[];
  maps: string[];
  agents: string[];
  moment_types: Array<{ key: string; label: string }>;
  platforms: string[];
}

export interface CleanupArtifact {
  id: number;
  kind: string;
  path: string;
  size_bytes: number | null;
  exists: boolean;
  deletable: boolean;
  reason: string;
  clip_id: number | null;
  created_at: string;
}

export interface CleanupPreview {
  artifacts: CleanupArtifact[];
  partials: Array<{ path: string; size_bytes: number }>;
  deletable_bytes: number;
  note: string;
}

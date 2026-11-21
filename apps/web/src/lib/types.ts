export interface StandardizedError {
  code: string;
  reason: string;
  impact: string;
  solution: string;
  next_action: string;
  cta_label?: string;
  cta_href?: string;
  http_status?: number | null;
}

export interface WorkflowStepItem {
  step_number: number;
  step_key: string;
  title: string;
  status: string;
  summary: string;
  href: string;
  updated_at?: string | null;
}

export interface QualityGateItem {
  gate_code: string;
  gate_name: string;
  status: string;
  details: Record<string, unknown>;
}

export interface BlockerItem {
  code: string;
  severity: string;
  title: string;
  cause: string;
  impact: string;
  solution: string;
  cta_label: string;
  cta_href: string;
}

export interface WorkflowState {
  steps: WorkflowStepItem[];
  counts: {
    demand_groups: number;
    research_requests: number;
    waiting_requests: number;
    research_batches: number;
    pending_approvals: number;
    keyword_mappings: number;
    content_briefs: number;
  };
  gates: QualityGateItem[];
  evidence_summary: {
    metrics_rows_count: number;
    organic_rows_count: number;
    duplicate_rows_count: number;
    missing_volume_count: number;
    missing_kd_count: number;
    missing_intent_count: number;
    source_coverage_ratio: number;
    low_volume_keywords: string[];
    serp_verified: boolean;
    serp_status: string;
    can_generate_official_brief: boolean;
    ready_for_brief: boolean;
  };
  blockers: BlockerItem[];
  next_action: {
    title: string;
    description: string;
    cta_label: string;
    cta_href: string;
  };
}

export interface ProjectItem {
  id: string;
  code: string;
  name: string;
  pillar_name: string;
  topic_pillar_code: string;
  topic_pillar_name: string;
  topic_type: string;
  split_axis: string;
  main_topic: string;
  content_code: string;
  content_title: string;
  primary_keyword_original: string;
  primary_keyword_current: string;
  secondary_keywords: string[];
  business_goal: string;
  target_audience: string;
  market: string;
  language: string;
  soft_article_min: number;
  soft_article_max: number;
  provenance: Record<string, unknown>;
  version: number;
  research_cycle: number;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  workflow?: WorkflowState;
}

export interface AIProviderInfo {
  provider: 'openai' | 'gemini' | 'claude' | 'mock';
  is_active: boolean;
  has_key: boolean;
  key_hint: string | null;
  secret_storage_mode: string;
  model_id: string;
  active_model_id: string;
  use_shared_model: boolean;
  analyst_model_id: string | null;
  critic_model_id: string | null;
  endpoint_url: string;
  auto_latest: boolean;
  downgrade_threshold: number;
  fallback_chain: string[];
  failure_counts: Record<string, number>;
  last_downgrade_reason: string | null;
  last_downgrade_at: string | null;
  connection_status: 'NOT_CONFIGURED' | 'READY_TO_TEST' | 'TESTING' | 'CONNECTED' | 'ERROR';
  last_tested_at: string | null;
  last_latency_ms: number | null;
  last_error_code: string | null;
  last_error: StandardizedError | null;
  updated_at: string | null;
}

export interface DemandGroupItem {
  id: string;
  name: string;
  user_need: string;
  coverage_type: string;
  assumed_page_type: string;
  assumed_intent: string;
  seed_keywords: string[];
  related_keywords: string[];
  supporting_evidence: string[];
  source_refs: string[];
  strongest_counterargument: string;
  missing_data: string[];
  next_action: string;
  recommended_semrush_report: string;
  boundary_note: string;
  business_relevance_note: string;
  critique_history: Array<{ stage: string; note: string }>;
  status: string;
  is_promoted: boolean;
}

export interface KeywordCandidateItem {
  id: string;
  keyword: string;
  candidate_type: string;
  assumed_page_type: string;
  source_refs: string[];
  source_ref_valid: boolean;
  rationale: string;
  status: string;
}

export interface ResearchRequestItem {
  id: string;
  project_id: string;
  demand_group_id?: string | null;
  seed_keyword: string;
  report_type: 'KEYWORD_OVERVIEW' | 'RELATED' | 'QUESTIONS' | 'ORGANIC_RESULTS';
  market: string;
  purpose: string;
  expected_columns: string[];
  semrush_steps: string[];
  research_cycle: number;
  origin: string;
  status: string;
  created_at?: string | null;
}

export interface EvidenceRowItem {
  id: string;
  batch_id: string;
  row_type: 'METRICS' | 'ORGANIC_RESULTS';
  source_row_number: number;
  keyword: string;
  volume: number | null;
  kd: number | null;
  intent: string | null;
  cpc: number | null;
  serp_features: string | null;
  organic_url: string | null;
  organic_position: number | null;
  organic_title: string | null;
  organic_page_type: string | null;
  serp_result_type?: string;
  organic_domain?: string;
  organic_valid?: boolean;
  market: string;
  is_duplicate: boolean;
  warnings: string[];
}

export interface MappingEligibility {
  mapping_id: string;
  primary_keyword: string;
  policy_version: string;
  current_revision: number;
  content_fingerprint: string;
  eligible_official: boolean;
  recommended_content_status: string;
  serp_tier: string;
  serp_status: string;
  top10_verified: boolean;
  live_fingerprint?: string;
  evidence_drifted?: boolean;
  serp_evidence?: {
    selected_batch_id?: string | null;
    candidate_snapshots_count?: number;
    conflicts_with_prior_snapshot?: boolean;
    valid_organic_count?: number;
    snapshot_identity?: {
      batch_id?: string | null;
      observed_at?: string | null;
      timestamp_kind?: string;
      keyword_binding_source?: string;
    } | null;
  };
  approval_state: string;
  blockers: StandardizedError[];
  warnings: Array<{ code: string; message: string }>;
  evidence_refs: string[];
  gate_statuses: Record<string, string>;
}

export interface CritiqueItem {
  id: string;
  research_cycle?: number;
  round_number: number;
  supporting_evidence: string[];
  counterarguments: string[];
  missing_data: string[];
  changes_from_evidence?: string[];
  followup_requests: Array<{ seed_keyword: string; report_type: string; purpose: string }>;
  next_action: string;
  decision_status: string;
  created_at?: string | null;
}

export interface KeywordMappingItem {
  id: string;
  logical_key?: string;
  revision: number;
  content_fingerprint?: string;
  primary_keyword: string;
  secondary_keywords: string[];
  page_type: string;
  proposed_url: string;
  volume: number | null;
  kd: number | null;
  intent: string | null;
  metrics_source: string;
  priority: string;
  business_value: string;
  effort: string;
  merge_split_proposal: string;
  serp_status: string;
  content_status: string;
  evidence: string[];
  is_approved: boolean;
  approved_revision?: number | null;
  approved_fingerprint?: string | null;
  approved_at: string | null;
  eligibility?: MappingEligibility;
}

export interface OpportunityItem {
  id: string;
  keyword_mapping_id: string | null;
  demand_group_name: string;
  opportunity_kind: 'ARTICLE_OPPORTUNITY' | 'NON_ARTICLE_ASSET' | 'RESEARCH_GAP';
  page_type: string;
  counts_toward_article_quota: boolean;
  title_suggestion: string;
  primary_keyword: string;
  priority: string;
  status: string;
  rationale: string;
  evidence: string[];
}

export interface ApprovalItem {
  id: string;
  approval_type: string;
  target_ref: string;
  target_revision?: number | null;
  target_fingerprint?: string | null;
  title: string;
  original_value: string;
  proposed_value: string;
  rationale: string;
  evidence: string[];
  impact: string;
  scope: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'NEED_MORE_EVIDENCE' | 'SUPERSEDED';
  decision_note: string;
  decided_by: string;
  version: number;
  created_at: string | null;
  decided_at: string | null;
}

export interface ContentBriefItem {
  id: string;
  keyword_mapping_id?: string | null;
  mapping_revision?: number | null;
  mapping_fingerprint?: string | null;
  is_stale?: boolean;
  stale_reasons?: string[];
  recorded_brief_mode?: 'OFFICIAL' | 'DRAFT';
  eligibility_snapshot?: Record<string, unknown>;
  br_code: string;
  content_type: string;
  priority: string;
  brief_mode: 'OFFICIAL' | 'DRAFT';
  status: string;
  primary_keyword: string;
  secondary_keywords: string[];
  metrics: Record<string, unknown>;
  proposed_url: string;
  target_audience: string;
  search_intent_status: 'ASSUMED' | 'VERIFIED';
  search_intent_summary: string;
  article_goal: string;
  seo_title: string;
  h1: string;
  meta_description: string;
  cta: string;
  internal_links: Array<{ anchor: string; target_url: string; reason: string }>;
  outline: Array<{ level: string; heading: string; notes?: string; children?: Array<{ level: string; heading: string }> }>;
  seo_checklist: string[];
  writing_strategy: {
    scope: string;
    per_heading_enforcement: boolean;
    editor_autonomy_note: string;
    primary_formula: string;
    supporting_formulas: string[];
    rationale: string;
    opening_ideas: string[];
    engagement_tactics: Array<{ number: number; code: string; text: string }>;
    title_variants?: string[];
  };
  version: number;
}

export interface ExportHistoryItem {
  id: string;
  export_format: string;
  filename: string;
  brief_mode: string;
  recorded_brief_mode: string;
  is_superseded: boolean;
  freshness_status: 'CURRENT' | 'OUTDATED_SUPERSEDED';
  superseded_reason: string;
  created_at: string | null;
  download_url: string;
  historical_download_url: string;
}

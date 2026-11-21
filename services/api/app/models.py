from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}_{raw}" if prefix else raw


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("prj"))
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    pillar_name: Mapped[str] = mapped_column(String(200), default="")
    topic_pillar_code: Mapped[str] = mapped_column(String(64), default="")
    topic_pillar_name: Mapped[str] = mapped_column(String(255), default="")
    topic_type: Mapped[str] = mapped_column(String(120), default="")
    split_axis: Mapped[str] = mapped_column(String(200), default="")
    main_topic: Mapped[str] = mapped_column(String(255), default="")
    content_code: Mapped[str] = mapped_column(String(64), default="")
    content_title: Mapped[str] = mapped_column(String(300), default="")
    primary_keyword_original: Mapped[str] = mapped_column(String(300), default="")
    primary_keyword_current: Mapped[str] = mapped_column(String(300), default="")
    secondary_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    business_goal: Mapped[str] = mapped_column(Text, default="")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    market: Mapped[str] = mapped_column(String(32), default="VN")
    language: Mapped[str] = mapped_column(String(32), default="vi")
    soft_article_min: Mapped[int] = mapped_column(Integer, default=5)
    soft_article_max: Mapped[int] = mapped_column(Integer, default=7)
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    research_cycle: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="READY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TaxonomyPillar(Base):
    __tablename__ = "taxonomy_pillars"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("pil"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_sheet: Mapped[str] = mapped_column(String(120), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TopicPillar(Base):
    __tablename__ = "topic_pillars"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("tp"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    taxonomy_pillar_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("taxonomy_pillars.id", ondelete="SET NULL"), nullable=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    pillar_name: Mapped[str] = mapped_column(String(255), default="")
    topic_type: Mapped[str] = mapped_column(String(120), default="")
    split_axis: Mapped[str] = mapped_column(String(200), default="")
    main_topic: Mapped[str] = mapped_column(String(255), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_sheet: Mapped[str] = mapped_column(String(120), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContentCode(Base):
    __tablename__ = "content_codes"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("cc"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    topic_pillar_code: Mapped[str] = mapped_column(String(64), default="")
    code: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    content_type_hint: Mapped[str] = mapped_column(String(64), default="UNKNOWN")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_sheet: Mapped[str] = mapped_column(String(120), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceKeyword(Base):
    __tablename__ = "source_keywords"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("skw"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    topic_pillar_code: Mapped[str] = mapped_column(String(64), default="")
    content_code: Mapped[str] = mapped_column(String(64), default="")
    keyword: Mapped[str] = mapped_column(String(300), index=True)
    keyword_normalized: Mapped[str] = mapped_column(String(300), index=True)
    role: Mapped[str] = mapped_column(String(32), default="SECONDARY")
    is_original: Mapped[bool] = mapped_column(Boolean, default=True)
    source_ref: Mapped[str] = mapped_column(String(160), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_sheet: Mapped[str] = mapped_column(String(120), default="")
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectSnapshot(Base):
    __tablename__ = "project_snapshots"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("snp"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200), default="update")
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectEvent(Base):
    __tablename__ = "project_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("evt"))
    project_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(24), default="INFO")
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("project_id", "step_number", name="uq_project_step"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("stp"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    step_number: Mapped[int] = mapped_column(Integer)
    step_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="NOT_STARTED")
    summary: Mapped[str] = mapped_column(Text, default="")
    blocker_json: Mapped[str] = mapped_column(Text, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DemandGroup(Base):
    __tablename__ = "demand_groups"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("dg"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    user_need: Mapped[str] = mapped_column(Text, default="")
    coverage_type: Mapped[str] = mapped_column(String(40), default="COVERED")
    assumed_page_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    assumed_intent: Mapped[str] = mapped_column(String(64), default="UNVERIFIED")
    seed_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    related_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    supporting_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    strongest_counterargument: Mapped[str] = mapped_column(Text, default="")
    missing_data_json: Mapped[str] = mapped_column(Text, default="[]")
    next_action: Mapped[str] = mapped_column(Text, default="")
    recommended_semrush_report: Mapped[str] = mapped_column(String(64), default="KEYWORD_OVERVIEW")
    boundary_note: Mapped[str] = mapped_column(Text, default="")
    business_relevance_note: Mapped[str] = mapped_column(Text, default="")
    critique_history_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(40), default="RESEARCH_CANDIDATE")
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KeywordCandidate(Base):
    __tablename__ = "keyword_candidates"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("kwc"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    demand_group_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("demand_groups.id", ondelete="SET NULL"), nullable=True)
    keyword: Mapped[str] = mapped_column(String(300))
    keyword_normalized: Mapped[str] = mapped_column(String(300), index=True)
    candidate_type: Mapped[str] = mapped_column(String(32), default="SEED_PROPOSAL")
    assumed_page_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    source_ref_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    rationale: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="RESEARCH_CANDIDATE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("air"))
    project_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(40))
    requested_model: Mapped[str] = mapped_column(String(120), default="")
    actual_model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1.6")
    schema_version: Mapped[str] = mapped_column(String(40), default="1.6.0")
    research_cycle: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    fallback_events_json: Mapped[str] = mapped_column(Text, default="[]")
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(40), default="COMPLETED")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Critique(Base):
    __tablename__ = "critiques"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("crt"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    ai_run_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("ai_runs.id", ondelete="SET NULL"), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), default="PRE_SEMRUSH")
    research_cycle: Mapped[int] = mapped_column(Integer, default=1)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    supporting_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    counterarguments_json: Mapped[str] = mapped_column(Text, default="[]")
    missing_data_json: Mapped[str] = mapped_column(Text, default="[]")
    changes_from_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    followup_requests_json: Mapped[str] = mapped_column(Text, default="[]")
    next_action: Mapped[str] = mapped_column(Text, default="")
    decision_status: Mapped[str] = mapped_column(String(40), default="REVIEW_REQUIRED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchRequest(Base):
    __tablename__ = "research_requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rr"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    demand_group_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("demand_groups.id", ondelete="SET NULL"), nullable=True)
    seed_keyword: Mapped[str] = mapped_column(String(300))
    report_type: Mapped[str] = mapped_column(String(40))
    market: Mapped[str] = mapped_column(String(32), default="VN")
    purpose: Mapped[str] = mapped_column(Text, default="")
    expected_columns_json: Mapped[str] = mapped_column(Text, default="[]")
    semrush_steps_json: Mapped[str] = mapped_column(Text, default="[]")
    research_cycle: Mapped[int] = mapped_column(Integer, default=1)
    origin: Mapped[str] = mapped_column(String(32), default="ANALYST")
    status: Mapped[str] = mapped_column(String(40), default="WAITING_USER")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FileUpload(Base):
    __tablename__ = "file_uploads"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("upl"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    research_request_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("research_requests.id", ondelete="SET NULL"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(40), default="SEMRUSH_IMPORT")
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    file_format: Mapped[str] = mapped_column(String(16), default="csv")
    sheet_name: Mapped[str] = mapped_column(String(120), default="")
    encoding: Mapped[str] = mapped_column(String(32), default="utf-8")
    delimiter: Mapped[str] = mapped_column(String(8), default=",")
    locale: Mapped[str] = mapped_column(String(16), default="en-US")
    row_count_total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="PREVIEWED")
    preview_meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchBatch(Base):
    __tablename__ = "research_batches"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("bat"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    research_request_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("research_requests.id", ondelete="SET NULL"), nullable=True)
    file_upload_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("file_uploads.id", ondelete="SET NULL"), nullable=True)
    report_type: Mapped[str] = mapped_column(String(40), default="KEYWORD_OVERVIEW")
    market: Mapped[str] = mapped_column(String(32), default="VN")
    locale: Mapped[str] = mapped_column(String(16), default="en-US")
    column_mapping_json: Mapped[str] = mapped_column(Text, default="{}")
    total_raw_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_normalized_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows_detected: Mapped[int] = mapped_column(Integer, default=0)
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(40), default="PROCESS_COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceRow(Base):
    __tablename__ = "evidence_rows"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ev"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[str] = mapped_column(String(40), ForeignKey("research_batches.id", ondelete="CASCADE"), index=True)
    row_type: Mapped[str] = mapped_column(String(32), default="METRICS")  # METRICS | ORGANIC_RESULTS
    source_row_number: Mapped[int] = mapped_column(Integer, default=1)
    keyword: Mapped[str] = mapped_column(String(300), default="", index=True)
    keyword_normalized: Mapped[str] = mapped_column(String(300), default="", index=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kd: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cpc: Mapped[float | None] = mapped_column(Float, nullable=True)
    serp_features: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Organic results specific fields (NEVER conflated with metrics!)
    organic_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    organic_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    organic_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    organic_page_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # V1.6.1 SERP provenance fields
    serp_result_type: Mapped[str] = mapped_column(String(40), default="ORGANIC")  # ORGANIC | AI_OVERVIEW | NON_ORGANIC
    organic_domain: Mapped[str] = mapped_column(String(255), default="")
    organic_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    market: Mapped[str] = mapped_column(String(32), default="VN")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_row_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KeywordEvidenceLink(Base):
    __tablename__ = "keyword_evidence_links"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("kel"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source_keyword_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("source_keywords.id", ondelete="SET NULL"), nullable=True)
    evidence_row_id: Mapped[str] = mapped_column(String(40), ForeignKey("evidence_rows.id", ondelete="CASCADE"), index=True)
    keyword_normalized: Mapped[str] = mapped_column(String(300), index=True)
    match_type: Mapped[str] = mapped_column(String(32), default="EXACT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityGate(Base):
    __tablename__ = "quality_gates"
    __table_args__ = (UniqueConstraint("project_id", "gate_code", name="uq_project_gate"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("qg"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    gate_code: Mapped[str] = mapped_column(String(16))
    gate_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="NOT_STARTED")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("apr"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    approval_type: Mapped[str] = mapped_column(String(48))
    target_ref: Mapped[str] = mapped_column(String(120), default="")
    target_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    original_value: Mapped[str] = mapped_column(Text, default="")
    proposed_value: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    impact: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(32), default="BRIEF_ELIGIBILITY")
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING|APPROVED|REJECTED|NEED_MORE_EVIDENCE|SUPERSEDED
    decision_note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(120), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KeywordMapping(Base):
    __tablename__ = "keyword_mappings"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("map"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    demand_group_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("demand_groups.id", ondelete="SET NULL"), nullable=True)
    logical_key: Mapped[str] = mapped_column(String(200), default="", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    content_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    primary_keyword: Mapped[str] = mapped_column(String(300))
    secondary_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    page_type: Mapped[str] = mapped_column(String(32), default="ARTICLE")
    proposed_url: Mapped[str] = mapped_column(String(300), default="")
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kd: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metrics_source: Mapped[str] = mapped_column(String(255), default="")
    metrics_evidence_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    priority: Mapped[str] = mapped_column(String(24), default="P2")
    business_value: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    effort: Mapped[str] = mapped_column(String(32), default="MEDIUM")
    merge_split_proposal: Mapped[str] = mapped_column(Text, default="")
    serp_status: Mapped[str] = mapped_column(String(40), default="SERP_NOT_VERIFIED")
    serp_evidence_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    content_status: Mapped[str] = mapped_column(String(40), default="SERP_NOT_VERIFIED")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MappingRevision(Base):
    """Immutable audit trail of every KeywordMapping revision & content fingerprint."""
    __tablename__ = "mapping_revisions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("mrev"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    keyword_mapping_id: Mapped[str] = mapped_column(String(40), ForeignKey("keyword_mappings.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ArticleOpportunity(Base):
    __tablename__ = "article_opportunities"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("opp"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    keyword_mapping_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("keyword_mappings.id", ondelete="SET NULL"), nullable=True)
    demand_group_name: Mapped[str] = mapped_column(String(255))
    opportunity_kind: Mapped[str] = mapped_column(String(32), default="ARTICLE_OPPORTUNITY")
    page_type: Mapped[str] = mapped_column(String(32), default="ARTICLE")
    counts_toward_article_quota: Mapped[bool] = mapped_column(Boolean, default=True)
    title_suggestion: Mapped[str] = mapped_column(String(300), default="")
    primary_keyword: Mapped[str] = mapped_column(String(300), default="")
    priority: Mapped[str] = mapped_column(String(24), default="P2")
    status: Mapped[str] = mapped_column(String(40), default="SERP_NOT_VERIFIED")
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContentBrief(Base):
    __tablename__ = "content_briefs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("br"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    keyword_mapping_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("keyword_mappings.id", ondelete="SET NULL"), nullable=True)
    mapping_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mapping_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    eligibility_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    br_code: Mapped[str] = mapped_column(String(40))
    content_type: Mapped[str] = mapped_column(String(32), default="ARTICLE")
    priority: Mapped[str] = mapped_column(String(24), default="P1")
    brief_mode: Mapped[str] = mapped_column(String(24), default="DRAFT")
    status: Mapped[str] = mapped_column(String(40), default="SERP_NOT_VERIFIED")
    primary_keyword: Mapped[str] = mapped_column(String(300))
    secondary_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    proposed_url: Mapped[str] = mapped_column(String(300), default="")
    target_audience: Mapped[str] = mapped_column(Text, default="")
    search_intent_status: Mapped[str] = mapped_column(String(40), default="ASSUMED")
    search_intent_summary: Mapped[str] = mapped_column(Text, default="")
    article_goal: Mapped[str] = mapped_column(Text, default="")
    seo_title: Mapped[str] = mapped_column(String(300), default="")
    h1: Mapped[str] = mapped_column(String(300), default="")
    meta_description: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(Text, default="")
    internal_links_json: Mapped[str] = mapped_column(Text, default="[]")
    outline_json: Mapped[str] = mapped_column(Text, default="[]")
    seo_checklist_json: Mapped[str] = mapped_column(Text, default="[]")
    writing_strategy_json: Mapped[str] = mapped_column(Text, default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BriefVersion(Base):
    __tablename__ = "brief_versions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("brv"))
    brief_id: Mapped[str] = mapped_column(String(40), ForeignKey("content_briefs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExportRecord(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("exp"))
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    export_format: Mapped[str] = mapped_column(String(24))
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    brief_mode: Mapped[str] = mapped_column(String(24), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIProviderSetting(Base):
    """Stores ONLY non-secret metadata and secret_ref. NEVER plaintext API keys!"""
    __tablename__ = "ai_provider_settings"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    secret_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    secret_storage_mode: Mapped[str] = mapped_column(String(32), default="none")
    key_hint: Mapped[str | None] = mapped_column(String(24), nullable=True)
    model_id: Mapped[str] = mapped_column(String(120), default="")
    active_model_id: Mapped[str] = mapped_column(String(120), default="")
    use_shared_model: Mapped[bool] = mapped_column(Boolean, default=True)
    analyst_model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    critic_model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    endpoint_url: Mapped[str] = mapped_column(String(300), default="")
    auto_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    downgrade_threshold: Mapped[int] = mapped_column(Integer, default=3)
    fallback_chain_json: Mapped[str] = mapped_column(Text, default="[]")
    failure_counts_json: Mapped[str] = mapped_column(Text, default="{}")
    last_downgrade_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_downgrade_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="NOT_CONFIGURED")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

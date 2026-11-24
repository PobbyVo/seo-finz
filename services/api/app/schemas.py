from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, examples=["P08"])
    name: str = Field(..., min_length=1, max_length=200)
    pillar_name: str = ""
    topic_pillar_code: str = ""
    topic_pillar_name: str = ""
    topic_type: str = ""
    split_axis: str = ""
    main_topic: str = ""
    content_code: str = ""
    content_title: str = ""
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    business_goal: str = ""
    target_audience: str = ""
    market: str = "VN"
    language: str = "vi"
    soft_article_min: int = Field(default=5, ge=1, le=50)
    soft_article_max: int = Field(default=7, ge=1, le=50)


class ProjectUpdateRequest(BaseModel):
    code: str | None = None
    name: str | None = None
    pillar_name: str | None = None
    topic_pillar_code: str | None = None
    topic_pillar_name: str | None = None
    topic_type: str | None = None
    split_axis: str | None = None
    main_topic: str | None = None
    content_code: str | None = None
    content_title: str | None = None
    primary_keyword: str | None = None
    secondary_keywords: list[str] | None = None
    business_goal: str | None = None
    target_audience: str | None = None
    market: str | None = None
    language: str | None = None
    soft_article_min: int | None = Field(default=None, ge=1, le=50)
    soft_article_max: int | None = Field(default=None, ge=1, le=50)
    change_reason: str = "Cập nhật thông tin chủ đề"


class TopicSourceConfirmRequest(BaseModel):
    source_scope: Literal["CONTENT", "PILLAR"] = "CONTENT"
    exclude_keywords_without_volume: bool | None = None
    upload_id: str
    selected_topic_pillar_code: str = ""
    selected_content_code: str = ""
    pillar_name: str = ""
    topic_pillar_name: str = ""
    topic_type: str = ""
    split_axis: str = ""
    main_topic: str = ""
    content_title: str = ""
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    business_goal: str = ""
    target_audience: str = ""
    market: str = "VN"
    language: str = "vi"
    soft_article_min: int = 5
    soft_article_max: int = 7


class ResearchRequestCreateItem(BaseModel):
    demand_group_id: str | None = None
    seed_keyword: str = Field(..., min_length=1)
    report_type: str = Field(default="KEYWORD_OVERVIEW")  # KEYWORD_OVERVIEW | RELATED | QUESTIONS | ORGANIC_RESULTS
    market: str = "VN"
    purpose: str = ""
    origin: str = "MANUAL"


class ResearchRequestBatchCreate(BaseModel):
    items: list[ResearchRequestCreateItem]


class ImportConfirmRequest(BaseModel):
    upload_id: str
    research_request_id: str | None = None
    report_type: str = "KEYWORD_OVERVIEW"
    market: str = "VN"
    locale: str = "en-US"
    sheet_name: str | None = None
    target_keyword: str | None = None
    column_mapping: dict[str, str | None]


class CriticRunRequest(BaseModel):
    stage: str = "POST_SEMRUSH"  # PRE_SEMRUSH | POST_SEMRUSH


class FollowupApproveRequest(BaseModel):
    critique_id: str | None = None
    selected_indices: list[int] | None = None
    custom_items: list[ResearchRequestCreateItem] = Field(default_factory=list)


class ApprovalDecisionRequest(BaseModel):
    decision: str  # APPROVED | REJECTED | NEED_MORE_EVIDENCE
    decision_note: str = ""
    decided_by: str = "SEO Specialist"


class BriefGenerateRequest(BaseModel):
    allow_draft: bool = True
    mapping_ids: list[str] | None = None


class AISettingUpdateRequest(BaseModel):
    provider: str  # openai | gemini | claude | mock
    set_active: bool = True
    api_key: str | None = None
    model_id: str | None = None
    use_shared_model: bool = True
    analyst_model_id: str | None = None
    critic_model_id: str | None = None
    endpoint_url: str | None = None
    auto_latest: bool | None = None
    downgrade_threshold: int | None = Field(default=None, ge=1, le=10)
    fallback_chain: list[str] | None = None


class AITestConnectionRequest(BaseModel):
    provider: str
    api_key: str | None = None
    model_id: str | None = None
    endpoint_url: str | None = None
    auto_latest: bool | None = None
    downgrade_threshold: int | None = Field(default=None, ge=1, le=10)
    confirm_live_cost: bool = True


class CandidatePromoteRequest(BaseModel):
    action: str = "PROMOTE"  # PROMOTE | REQUEST_APPROVAL | OUT_OF_SCOPE


class ExportRequest(BaseModel):
    format: str = "xlsx"  # xlsx | csv | json | html

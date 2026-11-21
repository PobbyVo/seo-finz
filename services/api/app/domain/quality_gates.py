from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.taxonomy_parser import normalize_text
from app.models import (
    Approval,
    ContentBrief,
    DemandGroup,
    EvidenceRow,
    KeywordCandidate,
    KeywordMapping,
    Project,
    QualityGate,
    ResearchBatch,
    SourceKeyword,
)

GATE_DEFINITIONS: list[tuple[str, str]] = [
    ("F0", "Cấu trúc taxonomy & nguồn dữ liệu"),
    ("E0", "Đối chiếu source_refs AI với nguồn SQLite"),
    ("E1", "Chất lượng nhóm nhu cầu (không tách từ đồng nghĩa)"),
    ("E2", "Kiểm soát trùng nhu cầu & quan hệ nhóm"),
    ("F1", "Độ đầy đủ Volume/KD/Intent từ Semrush"),
    ("F2", "Chuẩn hóa locale, dedup & bảo toàn raw/normalized"),
    ("F3", "Liên quan Topic Pillar & giữ keyword B2B Volume thấp"),
    ("F4", "Thứ tự ưu tiên theo bằng chứng & không ngưỡng KD cứng"),
    ("F5", "Bằng chứng SERP (ORGANIC_RESULTS tùy chọn)"),
    ("F6", "Keyword Mapping, loại trang & người dùng phê duyệt"),
    ("F7", "Chất lượng Content Brief & Writing Strategy cấp toàn bài"),
]


def valid_source_refs_for_project(db: Session, project: Project) -> set[str]:
    refs: set[str] = set()
    if project.topic_pillar_code:
        refs.add(f"TOPIC:{project.topic_pillar_code}")
        refs.add(project.topic_pillar_code)
    if project.content_code:
        refs.add(f"CONTENT:{project.content_code}")
        refs.add(project.content_code)
    for sk in db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all():
        if sk.source_ref:
            refs.add(sk.source_ref)
        if sk.content_code:
            refs.add(f"CONTENT:{sk.content_code}")
            refs.add(sk.content_code)
        if sk.topic_pillar_code:
            refs.add(f"TOPIC:{sk.topic_pillar_code}")
            refs.add(sk.topic_pillar_code)
    if not refs:
        refs.add(f"TOPIC:{project.code}")
        refs.add(project.code)
    return refs


def _upsert_gate(db: Session, project_id: str, code: str, name: str, status: str, details: dict[str, Any]) -> QualityGate:
    gate = (
        db.query(QualityGate)
        .filter(QualityGate.project_id == project_id, QualityGate.gate_code == code)
        .first()
    )
    if not gate:
        gate = QualityGate(project_id=project_id, gate_code=code, gate_name=name)
        db.add(gate)
    gate.gate_name = name
    gate.status = status
    gate.details_json = json.dumps(details, ensure_ascii=False)
    return gate


def evaluate_all_gates(db: Session, project: Project) -> dict[str, Any]:
    """
    Deterministic evaluation of F0..F7 and E0..E2.
    Enforces:
    - Never auto-promotes READY_FOR_BRIEF from Semrush metrics alone.
    - Preserves low-volume business-relevant keywords (LOW_VOLUME_BUT_RELEVANT).
    - Flags SERP_NOT_VERIFIED when no ORGANIC_RESULTS exist.
    """
    source_kws = db.query(SourceKeyword).filter(SourceKeyword.project_id == project.id).all()
    demand_groups = db.query(DemandGroup).filter(DemandGroup.project_id == project.id).all()
    candidates = db.query(KeywordCandidate).filter(KeywordCandidate.project_id == project.id).all()
    batches = db.query(ResearchBatch).filter(ResearchBatch.project_id == project.id).all()
    evidence_rows = db.query(EvidenceRow).filter(EvidenceRow.project_id == project.id).all()
    mappings = db.query(KeywordMapping).filter(KeywordMapping.project_id == project.id).all()
    approvals = db.query(Approval).filter(Approval.project_id == project.id).all()
    briefs = db.query(ContentBrief).filter(ContentBrief.project_id == project.id).all()

    valid_refs = valid_source_refs_for_project(db, project)

    # F0: Taxonomy & source data
    has_primary = bool(project.primary_keyword_original or project.primary_keyword_current)
    has_topic = bool(project.topic_pillar_code or project.topic_pillar_name or project.main_topic)
    f0_missing = []
    if not has_topic:
        f0_missing.append("Thiếu thông tin Topic Pillar / Chủ đề chính")
    if not has_primary:
        f0_missing.append("Thiếu Keyword chính gốc")
    f0_warnings = []
    if not project.business_goal:
        f0_warnings.append("Chưa nhập Mục tiêu kinh doanh (không tự suy đoán)")
    if not project.target_audience:
        f0_warnings.append("Chưa nhập Đối tượng độc giả (không tự suy đoán)")
    f0_status = "PASSED" if (has_topic and has_primary and not f0_warnings) else ("WARNING" if (has_topic and has_primary) else "FAILED")
    _upsert_gate(db, project.id, "F0", "Cấu trúc taxonomy & nguồn dữ liệu", f0_status, {
        "source_keywords_count": len(source_kws),
        "missing": f0_missing,
        "warnings": f0_warnings,
    })

    # E0: Source refs provenance check on AI outputs
    invalid_ref_groups = []
    for dg in demand_groups:
        refs = json.loads(dg.source_refs_json or "[]")
        if not refs or any(r not in valid_refs for r in refs):
            invalid_ref_groups.append(dg.name)
    invalid_candidates = [c.keyword for c in candidates if not c.source_ref_valid]
    if not demand_groups:
        e0_status = "NOT_STARTED"
    elif invalid_ref_groups or invalid_candidates:
        e0_status = "WARNING"
    else:
        e0_status = "PASSED"
    _upsert_gate(db, project.id, "E0", "Đối chiếu source_refs AI với nguồn SQLite", e0_status, {
        "valid_refs_count": len(valid_refs),
        "uncertain_groups": invalid_ref_groups,
        "uncertain_candidates": invalid_candidates,
    })

    # E1 & E2: Demand group quality & overlap
    if not demand_groups:
        _upsert_gate(db, project.id, "E1", "Chất lượng nhóm nhu cầu (không tách từ đồng nghĩa)", "NOT_STARTED", {})
        _upsert_gate(db, project.id, "E2", "Kiểm soát trùng nhu cầu & quan hệ nhóm", "NOT_STARTED", {})
    else:
        missing_counter = [dg.name for dg in demand_groups if not (dg.strongest_counterargument or "").strip()]
        overlaps = [dg.name for dg in demand_groups if dg.coverage_type == "OVERLAP"]
        _upsert_gate(db, project.id, "E1", "Chất lượng nhóm nhu cầu (không tách từ đồng nghĩa)", "WARNING" if missing_counter else "PASSED", {
            "demand_groups_count": len(demand_groups),
            "missing_counterargument": missing_counter,
        })
        _upsert_gate(db, project.id, "E2", "Kiểm soát trùng nhu cầu & quan hệ nhóm", "WARNING" if overlaps else "PASSED", {
            "overlap_groups": overlaps,
        })

    # F1 & F2: Evidence metrics completeness, locale & dedup
    metric_rows = [r for r in evidence_rows if r.row_type == "METRICS" and not r.is_duplicate]
    dup_rows = [r for r in evidence_rows if r.is_duplicate]
    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS" and not r.is_duplicate]

    missing_vol_kws = [r.keyword for r in metric_rows if r.volume is None]
    missing_kd_kws = [r.keyword for r in metric_rows if r.kd is None]
    missing_intent_kws = [r.keyword for r in metric_rows if not r.intent]
    market_mismatch = [b.id for b in batches if b.market and project.market and b.market.upper() != project.market.upper()]

    # Coverage of source keywords
    evidence_kw_norms = {r.keyword_normalized for r in metric_rows}
    source_norms = [sk.keyword_normalized for sk in source_kws]
    if project.primary_keyword_original and normalize_text(project.primary_keyword_original) not in source_norms:
        source_norms.append(normalize_text(project.primary_keyword_original))
    matched_source = [k for k in source_norms if k in evidence_kw_norms]
    coverage_ratio = round(len(matched_source) / len(source_norms), 2) if source_norms else 0.0

    if not metric_rows:
        f1_status = "NOT_STARTED"
    elif missing_kd_kws or missing_vol_kws or missing_intent_kws or market_mismatch or coverage_ratio < 0.5:
        f1_status = "WARNING"
    else:
        f1_status = "PASSED"

    _upsert_gate(db, project.id, "F1", "Độ đầy đủ Volume/KD/Intent từ Semrush", f1_status, {
        "metrics_rows": len(metric_rows),
        "missing_volume_count": len(missing_vol_kws),
        "missing_kd_count": len(missing_kd_kws),
        "missing_intent_count": len(missing_intent_kws),
        "source_coverage_ratio": coverage_ratio,
        "market_mismatch_batches": market_mismatch,
        "error_codes": [c for c, cnt in [("KD_MISSING", len(missing_kd_kws)), ("VOLUME_MISSING", len(missing_vol_kws)), ("INTENT_MISSING", len(missing_intent_kws))] if cnt > 0],
    })

    f2_status = "NOT_STARTED" if not batches else "PASSED"
    _upsert_gate(db, project.id, "F2", "Chuẩn hóa locale, dedup & bảo toàn raw/normalized", f2_status, {
        "batches_count": len(batches),
        "duplicate_rows_preserved_without_summing": len(dup_rows),
        "total_raw_rows": sum(b.total_raw_rows for b in batches),
        "total_normalized_rows": sum(b.total_normalized_rows for b in batches),
    })

    # F3: Low volume but business relevant preservation (NEVER drop by hard threshold!)
    low_vol_kws = [r.keyword for r in metric_rows if r.volume is not None and r.volume < 100]
    f3_status = "NOT_STARTED" if not metric_rows else "PASSED"
    _upsert_gate(db, project.id, "F3", "Liên quan Topic Pillar & giữ keyword B2B Volume thấp", f3_status, {
        "low_volume_preserved_count": len(low_vol_kws),
        "low_volume_examples": low_vol_kws[:8],
        "hard_volume_cutoff_applied": False,
    })

    # F4: Evidence-based priority, no hard KD cutoff
    f4_status = "NOT_STARTED" if not mappings else "PASSED"
    _upsert_gate(db, project.id, "F4", "Thứ tự ưu tiên theo bằng chứng & không ngưỡng KD cứng", f4_status, {
        "mappings_count": len(mappings),
        "hard_kd_cutoff_applied": False,
    })

    # F5: SERP evidence (ORGANIC_RESULTS optional, NEVER manual entry required)
    has_serp = len(organic_rows) > 0
    f5_status = "PASSED" if has_serp else ("WARNING" if metric_rows else "NOT_STARTED")
    _upsert_gate(db, project.id, "F5", "Bằng chứng SERP (ORGANIC_RESULTS tùy chọn)", f5_status, {
        "organic_rows_count": len(organic_rows),
        "serp_status": "SERP_VERIFIED" if has_serp else "SERP_NOT_VERIFIED",
        "note": (
            f"Đã xác minh bằng {len(organic_rows)} dòng ORGANIC_RESULTS từ Semrush."
            if has_serp
            else "Chưa có file ORGANIC_RESULTS -> gắn SERP_NOT_VERIFIED; chỉ cho phép kế hoạch/brief DỰ THẢO."
        ),
    })

    # F6: Mapping & human approval (NEVER auto-approved!)
    pending_brief_approvals = [a for a in approvals if a.status == "PENDING" and a.scope == "BRIEF_ELIGIBILITY"]
    approved_mappings = [m for m in mappings if m.is_approved]
    if not mappings:
        f6_status = "NOT_STARTED"
    elif pending_brief_approvals or not approved_mappings:
        f6_status = "HOLD"
    else:
        f6_status = "PASSED"
    _upsert_gate(db, project.id, "F6", "Keyword Mapping, loại trang & người dùng phê duyệt", f6_status, {
        "mappings_total": len(mappings),
        "mappings_approved": len(approved_mappings),
        "pending_approvals": len(pending_brief_approvals),
    })

    # F7: Content Brief quality
    if not briefs:
        f7_status = "NOT_STARTED"
    else:
        official_briefs = [b for b in briefs if b.brief_mode == "OFFICIAL"]
        f7_status = "PASSED" if official_briefs else "WARNING"
    _upsert_gate(db, project.id, "F7", "Chất lượng Content Brief & Writing Strategy cấp toàn bài", f7_status, {
        "briefs_count": len(briefs),
        "official_briefs": len([b for b in briefs if b.brief_mode == "OFFICIAL"]),
        "draft_briefs": len([b for b in briefs if b.brief_mode != "OFFICIAL"]),
    })

    db.commit()

    # Official brief eligibility: MUST have F0 valid, F1 has metrics, F5 SERP verified, AND F6 user approved!
    can_generate_official_brief = (
        f0_status in ("PASSED", "WARNING")
        and len(metric_rows) > 0
        and has_serp
        and f6_status == "PASSED"
    )

    gates = db.query(QualityGate).filter(QualityGate.project_id == project.id).all()
    gate_order = {code: idx for idx, (code, _) in enumerate(GATE_DEFINITIONS)}
    gates.sort(key=lambda g: gate_order.get(g.gate_code, 99))

    return {
        "gates": [
            {
                "gate_code": g.gate_code,
                "gate_name": g.gate_name,
                "status": g.status,
                "details": json.loads(g.details_json or "{}"),
            }
            for g in gates
        ],
        "summary": {
            "metrics_rows_count": len(metric_rows),
            "organic_rows_count": len(organic_rows),
            "duplicate_rows_count": len(dup_rows),
            "missing_volume_count": len(missing_vol_kws),
            "missing_kd_count": len(missing_kd_kws),
            "missing_intent_count": len(missing_intent_kws),
            "source_coverage_ratio": coverage_ratio,
            "low_volume_keywords": low_vol_kws,
            "serp_verified": has_serp,
            "serp_status": "SERP_VERIFIED" if has_serp else "SERP_NOT_VERIFIED",
            "can_generate_official_brief": can_generate_official_brief,
            "ready_for_brief": can_generate_official_brief,
        },
    }

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.eligibility_policy import (
    POLICY_VERSION,
    evaluate_brief_quality,
    evaluate_mapping_eligibility,
    evaluate_serp_for_keyword,
    load_project_policy_context,
    valid_source_refs_for_project,
    verify_batch_integrity,
)
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
    ("F0", "Cấu trúc taxonomy & thông tin đầu vào dự án"),
    ("E0", "Đối chiếu source_refs AI với nguồn SQLite"),
    ("E1", "Chất lượng nhóm nhu cầu (không tách từ đồng nghĩa)"),
    ("E2", "Kiểm soát trùng nhu cầu & quan hệ nhóm"),
    ("F1", "Độ đầy đủ Volume/KD/Intent theo đúng từ khóa & thị trường"),
    ("F2", "Toàn vẹn import, locale, dedup & raw/normalized"),
    ("F3", "Liên quan Topic Pillar, mục tiêu B2B & giữ Volume thấp"),
    ("F4", "Thứ tự ưu tiên có lập luận kiểm toán & không ngưỡng KD cứng"),
    ("F5", "Bằng chứng SERP theo từng từ khóa & thị trường"),
    ("F6", "Phê duyệt đúng phiên bản/fingerprint Keyword Mapping"),
    ("F7", "Chất lượng & tính mới của Content Brief đã sinh (hậu kiểm)"),
]


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
    Deterministic evaluation of F0..F7 and E0..E2 backed by the single authoritative
    `eligibility_policy`. Separates:
    - Project-level diagnostic summary
    - Per-mapping pre-generation eligibility (`mapping_eligibilities`)
    - Post-generation brief quality (F7)
    """
    ctx = load_project_policy_context(db, project)
    source_kws: list[SourceKeyword] = ctx["source_keywords"]
    demand_groups: list[DemandGroup] = list(ctx["demand_groups_by_id"].values())
    candidates = db.query(KeywordCandidate).filter(KeywordCandidate.project_id == project.id).all()
    batches: list[ResearchBatch] = list(ctx["batches_by_id"].values())
    uploads_by_id = ctx["uploads_by_id"]
    evidence_rows: list[EvidenceRow] = ctx["evidence_rows"]
    approvals: list[Approval] = ctx["approvals"]
    briefs: list[ContentBrief] = ctx["briefs"]
    valid_refs = ctx["valid_refs"]

    active_mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project.id, KeywordMapping.is_archived == False)  # noqa: E712
        .order_by(KeywordMapping.priority.asc(), KeywordMapping.created_at.asc())
        .all()
    )

    proj_market = (project.market or "VN").upper()

    # Evaluate authoritative per-mapping eligibility for every active mapping
    mapping_eligibilities: dict[str, dict[str, Any]] = {
        m.id: evaluate_mapping_eligibility(project, m, ctx)
        for m in active_mappings
    }

    # --- F0: Taxonomy & required project inputs ---
    has_primary = bool(project.primary_keyword_original or project.primary_keyword_current)
    has_topic = bool(project.topic_pillar_code or project.topic_pillar_name or project.main_topic)
    has_goal = bool((project.business_goal or "").strip())
    has_aud = bool((project.target_audience or "").strip())
    f0_missing = []
    if not has_topic:
        f0_missing.append("Thiếu thông tin Topic Pillar / Chủ đề chính")
    if not has_primary:
        f0_missing.append("Thiếu Keyword chính gốc")
    f0_warnings = []
    if not has_goal:
        f0_warnings.append("Chưa nhập Mục tiêu kinh doanh (bắt buộc cho Brief chính thức; hệ thống không tự đoán)")
    if not has_aud:
        f0_warnings.append("Chưa nhập Đối tượng độc giả (bắt buộc cho Brief chính thức; hệ thống không tự đoán)")
    f0_status = "PASSED" if (has_topic and has_primary and has_goal and has_aud) else ("WARNING" if (has_topic and has_primary) else "FAILED")
    _upsert_gate(db, project.id, "F0", GATE_DEFINITIONS[0][1], f0_status, {
        "source_keywords_count": len(source_kws),
        "missing": f0_missing,
        "warnings": f0_warnings,
    })

    # --- E0: AI source_refs provenance ---
    invalid_ref_groups = []
    for dg in demand_groups:
        refs = json.loads(dg.source_refs_json or "[]")
        if not refs or any(r not in valid_refs for r in refs) or dg.status == "UNCERTAIN":
            invalid_ref_groups.append(dg.name)
    invalid_candidates = [c.keyword for c in candidates if not c.source_ref_valid]
    if not demand_groups:
        e0_status = "NOT_STARTED"
    elif invalid_ref_groups:
        e0_status = "FAILED"
    elif invalid_candidates:
        e0_status = "WARNING"
    else:
        e0_status = "PASSED"
    _upsert_gate(db, project.id, "E0", GATE_DEFINITIONS[1][1], e0_status, {
        "valid_refs_count": len(valid_refs),
        "uncertain_groups": invalid_ref_groups,
        "uncertain_candidates": invalid_candidates,
    })

    # --- E1 & E2: Demand group quality & overlap ---
    if not demand_groups:
        _upsert_gate(db, project.id, "E1", GATE_DEFINITIONS[2][1], "NOT_STARTED", {})
        _upsert_gate(db, project.id, "E2", GATE_DEFINITIONS[3][1], "NOT_STARTED", {})
    else:
        missing_counter = [dg.name for dg in demand_groups if not (dg.strongest_counterargument or "").strip()]
        missing_ev = [dg.name for dg in demand_groups if not json.loads(dg.supporting_evidence_json or "[]")]
        overlaps = [dg for dg in demand_groups if dg.coverage_type == "OVERLAP"]
        unresolved_overlaps = [
            dg.name
            for dg in overlaps
            if any(
                m.demand_group_id == dg.id and mapping_eligibilities[m.id]["gate_statuses"].get("E2") != "PASSED"
                for m in active_mappings
            ) or not active_mappings
        ]
        e1_status = "WARNING" if (missing_counter or missing_ev) else "PASSED"
        e2_status = "HOLD" if unresolved_overlaps else "PASSED"
        _upsert_gate(db, project.id, "E1", GATE_DEFINITIONS[2][1], e1_status, {
            "demand_groups_count": len(demand_groups),
            "missing_counterargument": missing_counter,
            "missing_supporting_evidence": missing_ev,
        })
        _upsert_gate(db, project.id, "E2", GATE_DEFINITIONS[3][1], e2_status, {
            "overlap_groups": [dg.name for dg in overlaps],
            "unresolved_overlaps": unresolved_overlaps,
        })

    # --- F1: Per-keyword metrics completeness & market alignment ---
    metric_rows = [r for r in evidence_rows if r.row_type == "METRICS" and not r.is_duplicate]
    matching_market_metrics = [r for r in metric_rows if (r.market or proj_market).upper() == proj_market]
    dup_rows = [r for r in evidence_rows if r.is_duplicate]
    organic_rows = [r for r in evidence_rows if r.row_type == "ORGANIC_RESULTS"]
    valid_organic_rows = [
        r for r in organic_rows
        if not r.is_duplicate
        and getattr(r, "organic_valid", True)
        and (getattr(r, "serp_result_type", "ORGANIC") or "ORGANIC").upper() == "ORGANIC"
        and (r.market or proj_market).upper() == proj_market
    ]

    missing_vol_kws = [r.keyword for r in matching_market_metrics if r.volume is None]
    missing_kd_kws = [r.keyword for r in matching_market_metrics if r.kd is None]
    missing_intent_kws = [r.keyword for r in matching_market_metrics if not r.intent]
    market_mismatch = [b.id for b in batches if b.market and proj_market and b.market.upper() != proj_market]

    evidence_kw_norms = {r.keyword_normalized for r in matching_market_metrics}
    source_norms = [sk.keyword_normalized for sk in source_kws]
    if project.primary_keyword_original and normalize_text(project.primary_keyword_original) not in source_norms:
        source_norms.append(normalize_text(project.primary_keyword_original))
    matched_source = [k for k in source_norms if k in evidence_kw_norms]
    coverage_ratio = round(len(matched_source) / len(source_norms), 2) if source_norms else 0.0

    if not metric_rows:
        f1_status = "NOT_STARTED"
    elif not matching_market_metrics or market_mismatch:
        f1_status = "FAILED"
    elif missing_kd_kws or missing_vol_kws or coverage_ratio < 0.5:
        f1_status = "WARNING"
    else:
        f1_status = "PASSED"

    _upsert_gate(db, project.id, "F1", GATE_DEFINITIONS[4][1], f1_status, {
        "metrics_rows": len(metric_rows),
        "matching_market_metrics_rows": len(matching_market_metrics),
        "missing_volume_count": len(missing_vol_kws),
        "missing_kd_count": len(missing_kd_kws),
        "missing_intent_count": len(missing_intent_kws),
        "source_coverage_ratio": coverage_ratio,
        "market_mismatch_batches": market_mismatch,
        "error_codes": [
            c
            for c, cnt in [
                ("MARKET_MISMATCH", len(market_mismatch)),
                ("KD_MISSING", len(missing_kd_kws)),
                ("VOLUME_MISSING", len(missing_vol_kws)),
                ("INTENT_MISSING", len(missing_intent_kws)),
            ]
            if cnt > 0
        ],
    })

    # --- F2: Full tamper-evident import integrity (VERIFIED / UNVERIFIED / FAILED per batch) ---
    batch_integrity_by_id = ctx.get("batch_integrity_by_id") or {}
    batch_statuses: dict[str, str] = {}
    if not batches:
        f2_status = "NOT_STARTED"
        f2_issues: list[str] = []
    else:
        f2_issues = []
        any_failed = False
        any_unverified = False
        for b in batches:
            b_int = batch_integrity_by_id.get(b.id)
            if b_int is None:
                ok_b, issues_b = verify_batch_integrity(b, uploads_by_id, evidence_rows)
                b_stat = "VERIFIED" if ok_b else "FAILED"
                b_int = {"status": b_stat, "ok": ok_b, "issues": issues_b}
            batch_statuses[b.id] = b_int["status"]
            if b_int["status"] == "FAILED":
                any_failed = True
                f2_issues.extend(b_int["issues"])
            elif b_int["status"] == "UNVERIFIED":
                any_unverified = True
                f2_issues.extend(b_int["issues"])
        if any_failed:
            f2_status = "FAILED"
        elif any_unverified:
            f2_status = "WARNING"
        else:
            f2_status = "PASSED"
    _upsert_gate(db, project.id, "F2", GATE_DEFINITIONS[5][1], f2_status, {
        "batches_count": len(batches),
        "batch_statuses": batch_statuses,
        "integrity_issues": f2_issues,
        "duplicate_rows_preserved_without_summing": len(dup_rows),
        "total_raw_rows": sum(b.total_raw_rows for b in batches),
        "total_normalized_rows": sum(b.total_normalized_rows for b in batches),
    })

    # --- F3: Topical relevance & business rationale (NEVER passes merely because metrics exist!) ---
    low_vol_kws = [r.keyword for r in matching_market_metrics if r.volume is not None and r.volume < 100]
    if not metric_rows:
        f3_status = "NOT_STARTED"
    elif not has_topic or not has_goal or not has_aud:
        f3_status = "WARNING"
    elif not matched_source:
        f3_status = "WARNING"
    else:
        f3_status = "PASSED"
    _upsert_gate(db, project.id, "F3", GATE_DEFINITIONS[6][1], f3_status, {
        "has_business_goal": has_goal,
        "has_target_audience": has_aud,
        "matched_source_keywords_count": len(matched_source),
        "low_volume_preserved_count": len(low_vol_kws),
        "low_volume_examples": low_vol_kws[:8],
        "hard_volume_cutoff_applied": False,
    })

    # --- F4: Auditable priority/effort rationale (NEVER passes merely because mapping rows exist!) ---
    if not active_mappings:
        f4_status = "NOT_STARTED"
        f4_incomplete: list[str] = []
    else:
        f4_incomplete = [
            m.primary_keyword
            for m in active_mappings
            if mapping_eligibilities[m.id]["gate_statuses"].get("F4") != "PASSED"
        ]
        f4_status = "WARNING" if f4_incomplete else "PASSED"
    _upsert_gate(db, project.id, "F4", GATE_DEFINITIONS[7][1], f4_status, {
        "mappings_count": len(active_mappings),
        "incomplete_rationale_keywords": f4_incomplete,
        "hard_kd_cutoff_applied": False,
    })

    # --- F5: Per-keyword, per-market SERP provenance ---
    if active_mappings:
        serp_tiers = {m.id: mapping_eligibilities[m.id]["serp_tier"] for m in active_mappings}
        verified_mappings = [m for m in active_mappings if serp_tiers[m.id] in ("SERP_VERIFIED", "TOP_10_VERIFIED")]
        top10_mappings = [m for m in active_mappings if serp_tiers[m.id] == "TOP_10_VERIFIED"]
        partial_mappings = [m for m in active_mappings if serp_tiers[m.id] == "PARTIAL_SERP_EVIDENCE"]
        unverified_mappings = [m for m in active_mappings if serp_tiers[m.id] == "SERP_NOT_VERIFIED"]

        if len(verified_mappings) == len(active_mappings):
            f5_status = "PASSED"
            project_serp_status = "TOP_10_VERIFIED" if len(top10_mappings) == len(active_mappings) else "SERP_VERIFIED"
        elif verified_mappings or partial_mappings:
            f5_status = "WARNING"
            project_serp_status = "PARTIAL_SERP_EVIDENCE"
        else:
            f5_status = "WARNING" if metric_rows else "NOT_STARTED"
            project_serp_status = "SERP_NOT_VERIFIED"
        f5_details = {
            "valid_organic_rows_count": len(valid_organic_rows),
            "mappings_serp_verified": len(verified_mappings),
            "mappings_top10_verified": len(top10_mappings),
            "mappings_partial_serp": len(partial_mappings),
            "mappings_serp_not_verified": len(unverified_mappings),
            "serp_status": project_serp_status,
            "note": (
                f"{len(verified_mappings)}/{len(active_mappings)} mapping có đủ bằng chứng SERP theo đúng từ khóa & thị trường "
                f"({len(top10_mappings)} đạt Top 10 đầy đủ)."
            ),
        }
        any_serp_verified = len(verified_mappings) > 0
    else:
        # Before mappings exist, evaluate SERP against primary keyword only (never project-wide illusion)
        pk = project.primary_keyword_current or project.primary_keyword_original
        pk_serp = (
            evaluate_serp_for_keyword(
                project, pk, organic_rows, ctx["batches_by_id"], uploads_by_id,
                batch_integrity_by_id=batch_integrity_by_id,
            )
            if pk
            else None
        )
        if pk_serp and pk_serp["serp_sufficient"]:
            f5_status = "PASSED"
            project_serp_status = pk_serp["serp_tier"]
            any_serp_verified = True
        elif pk_serp and pk_serp["serp_tier"] == "PARTIAL_SERP_EVIDENCE":
            f5_status = "WARNING"
            project_serp_status = "PARTIAL_SERP_EVIDENCE"
            any_serp_verified = False
        else:
            f5_status = "WARNING" if metric_rows else "NOT_STARTED"
            project_serp_status = "SERP_NOT_VERIFIED"
            any_serp_verified = False
        f5_details = {
            "valid_organic_rows_count": len(valid_organic_rows),
            "serp_status": project_serp_status,
            "primary_keyword_serp": pk_serp,
            "note": pk_serp["sufficiency_reason"] if pk_serp else "Chưa có từ khóa chính hoặc file ORGANIC_RESULTS.",
        }
    _upsert_gate(db, project.id, "F5", GATE_DEFINITIONS[8][1], f5_status, f5_details)

    # --- F6: Exact Revision & Fingerprint Human Approvals ---
    pending_brief_approvals = [a for a in approvals if a.status == "PENDING" and a.scope == "BRIEF_ELIGIBILITY"]
    current_approved_mappings = [
        m for m in active_mappings
        if mapping_eligibilities[m.id]["approval_state"] == "APPROVED_CURRENT"
    ]
    stale_approved_mappings = [
        m for m in active_mappings
        if mapping_eligibilities[m.id]["approval_state"] == "STALE_SUPERSEDED"
    ]
    if not active_mappings:
        f6_status = "NOT_STARTED"
    elif pending_brief_approvals or stale_approved_mappings or not current_approved_mappings:
        f6_status = "HOLD"
    else:
        f6_status = "PASSED"
    _upsert_gate(db, project.id, "F6", GATE_DEFINITIONS[9][1], f6_status, {
        "mappings_total": len(active_mappings),
        "mappings_approved_current": len(current_approved_mappings),
        "mappings_needing_reapproval": len(stale_approved_mappings),
        "pending_approvals": len(pending_brief_approvals),
    })

    # --- F7: Post-Generation Brief Quality (Phase 2 — strictly separate from Phase 1 eligibility!) ---
    mappings_by_id = {m.id: m for m in active_mappings}
    brief_checks = [
        evaluate_brief_quality(
            b,
            mappings_by_id.get(b.keyword_mapping_id) if b.keyword_mapping_id else None,
            mapping_eligibilities.get(b.keyword_mapping_id) if b.keyword_mapping_id else None,
        )
        for b in briefs
    ]
    if not briefs:
        f7_status = "NOT_STARTED"
    else:
        failed_briefs = [bc for bc in brief_checks if not bc["passed"]]
        stale_briefs = [bc for bc in brief_checks if bc["is_stale"]]
        official_briefs = [bc for bc in brief_checks if bc["brief_mode"] == "OFFICIAL" and not bc["is_stale"]]
        if failed_briefs:
            f7_status = "FAILED"
        elif stale_briefs or not official_briefs:
            f7_status = "WARNING"
        else:
            f7_status = "PASSED"
    _upsert_gate(db, project.id, "F7", GATE_DEFINITIONS[10][1], f7_status, {
        "phase": "POST_GENERATION",
        "briefs_count": len(briefs),
        "official_briefs": len([bc for bc in brief_checks if bc["brief_mode"] == "OFFICIAL" and not bc["is_stale"]]),
        "draft_briefs": len([bc for bc in brief_checks if bc["brief_mode"] != "OFFICIAL"]),
        "stale_briefs": len([bc for bc in brief_checks if bc["is_stale"]]),
        "checks": brief_checks,
    })

    db.commit()

    eligible_mapping_ids = [
        m_id for m_id, dec in mapping_eligibilities.items() if dec["eligible_official"]
    ]
    can_generate_official_brief = len(eligible_mapping_ids) > 0

    gates = db.query(QualityGate).filter(QualityGate.project_id == project.id).all()
    gate_order = {code: idx for idx, (code, _) in enumerate(GATE_DEFINITIONS)}
    gates.sort(key=lambda g: gate_order.get(g.gate_code, 99))

    return {
        "policy_version": POLICY_VERSION,
        "gates": [
            {
                "gate_code": g.gate_code,
                "gate_name": g.gate_name,
                "status": g.status,
                "details": json.loads(g.details_json or "{}"),
            }
            for g in gates
        ],
        "mapping_eligibilities": mapping_eligibilities,
        "summary": {
            "policy_version": POLICY_VERSION,
            "metrics_rows_count": len(matching_market_metrics),
            "metrics_rows_total_all_markets": len(metric_rows),
            "organic_rows_count": len(valid_organic_rows),
            "duplicate_rows_count": len(dup_rows),
            "missing_volume_count": len(missing_vol_kws),
            "missing_kd_count": len(missing_kd_kws),
            "missing_intent_count": len(missing_intent_kws),
            "source_coverage_ratio": coverage_ratio,
            "low_volume_keywords": low_vol_kws,
            "serp_verified": any_serp_verified,
            "serp_status": project_serp_status,
            "eligible_official_mapping_ids": eligible_mapping_ids,
            "eligible_official_count": len(eligible_mapping_ids),
            "total_active_mappings": len(active_mappings),
            "can_generate_official_brief": can_generate_official_brief,
            "ready_for_brief": can_generate_official_brief,
        },
    }

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.eligibility_policy import compute_effective_brief_freshness
from app.domain.quality_gates import evaluate_all_gates
from app.models import (
    Approval,
    ContentBrief,
    Critique,
    DemandGroup,
    KeywordMapping,
    Project,
    ResearchBatch,
    ResearchRequest,
    WorkflowStep,
)

STEP_SPECS: list[tuple[int, str, str, str]] = [
    (1, "topic_setup", "01. Thiết lập chủ đề", "/steps/01-topic"),
    (2, "demand_map", "02. Bản đồ nhu cầu (AI)", "/steps/02-demand-map"),
    (3, "semrush_requests", "03. Yêu cầu Semrush", "/steps/03-semrush"),
    (4, "upload_mapping", "04. Tải file & ghép cột", "/steps/04-upload"),
    (5, "evidence_critic", "05. Kiểm tra dữ liệu & AI Critic", "/steps/05-evidence"),
    (6, "keyword_mapping", "06. Kế hoạch bài viết / Mapping", "/steps/06-mapping"),
    (7, "content_brief", "07. SEO Content Brief & Xuất", "/steps/07-brief"),
]

SEMRUSH_REPORT_GUIDES: dict[str, dict[str, Any]] = {
    "KEYWORD_OVERVIEW": {
        "columns": ["Keyword", "Volume", "KD %", "Intent", "CPC", "SERP Features"],
        "steps": [
            "Mở giao diện Semrush trên trình duyệt (tài khoản của bạn, KHÔNG cần API/MCP).",
            "Vào mục SEO → Keyword Research → Keyword Overview (hoặc Bulk Keyword Analysis).",
            "Chọn đúng thị trường (Market/Database, ví dụ: VN) và dán bộ keyword seed cần kiểm chứng.",
            "Xuất kết quả sang file CSV hoặc XLSX (đảm bảo có các cột Keyword, Volume, KD, Intent nếu tài khoản hiển thị).",
            "Quay lại Bước 04 của FinZ SEO Workbench, chọn đúng phiếu yêu cầu này và tải file lên.",
        ],
    },
    "RELATED": {
        "columns": ["Keyword", "Volume", "KD %", "Intent", "SERP Features"],
        "steps": [
            "Mở giao diện Semrush → Keyword Magic Tool.",
            "Nhập từ khóa seed, chọn đúng quốc gia/thị trường mục tiêu.",
            "Chuyển sang tab Related để xem các biến thể đồng nghĩa và chủ đề liền kề.",
            "Bấm Export → CSV hoặc XLSX (không cần lọc bỏ Volume thấp nếu liên quan B2B).",
            "Tải file xuất lên Bước 04 của FinZ SEO Workbench để đối chiếu trùng lặp nhu cầu.",
        ],
    },
    "QUESTIONS": {
        "columns": ["Keyword", "Volume", "KD %", "Intent", "SERP Features"],
        "steps": [
            "Mở giao diện Semrush → Keyword Magic Tool.",
            "Nhập từ khóa seed và chọn đúng thị trường.",
            "Bật bộ lọc Questions để lọc các câu hỏi thực tế của người tìm kiếm.",
            "Bấm Export → CSV hoặc XLSX.",
            "Tải file vào Bước 04 và ghép cột tương ứng.",
        ],
    },
    "ORGANIC_RESULTS": {
        "columns": ["Position", "Type (Organic/AI Overview)", "Domain", "URL", "Keyword (nếu có)"],
        "steps": [
            "Mở giao diện Semrush → Keyword Overview → phần SERP Analysis (hoặc Organic Results).",
            "Xuất bảng kết quả tự nhiên sang CSV/XLSX (hỗ trợ trực tiếp file SERP Analysis có cột Position, Type, Domain, URL).",
            "Lưu ý: Nếu không xuất được báo cáo này, bạn KHÔNG cần nhập tay URL — hệ thống sẽ gắn nhãn SERP_NOT_VERIFIED cho bản kế hoạch dự thảo.",
            "Khi tải lên Bước 04, chọn đúng phiếu Yêu cầu Semrush này để gắn chính xác từ khóa cho bảng SERP.",
        ],
    },
}


def ensure_workflow_steps(db: Session, project_id: str) -> list[WorkflowStep]:
    existing = {
        s.step_number: s
        for s in db.query(WorkflowStep).filter(WorkflowStep.project_id == project_id).all()
    }
    created = False
    for num, key, title, _href in STEP_SPECS:
        if num not in existing:
            st = WorkflowStep(
                project_id=project_id,
                step_number=num,
                step_key=key,
                title=title,
                status="READY" if num == 1 else "NOT_STARTED",
                summary="",
            )
            db.add(st)
            existing[num] = st
            created = True
    if created:
        db.commit()
    return [existing[num] for num, *_ in STEP_SPECS]


def refresh_workflow_state(db: Session, project: Project) -> dict[str, Any]:
    """Recompute authentic 7-step statuses, blockers, and next actions from SQLite & policy truth."""
    steps = ensure_workflow_steps(db, project.id)
    gate_eval = evaluate_all_gates(db, project)
    summary = gate_eval["summary"]
    elig_map = gate_eval["mapping_eligibilities"]

    dgs = db.query(DemandGroup).filter(DemandGroup.project_id == project.id).all()
    reqs = db.query(ResearchRequest).filter(ResearchRequest.project_id == project.id).all()
    batches = db.query(ResearchBatch).filter(ResearchBatch.project_id == project.id).all()
    critiques_post = (
        db.query(Critique)
        .filter(Critique.project_id == project.id, Critique.stage == "POST_SEMRUSH")
        .all()
    )
    mappings = (
        db.query(KeywordMapping)
        .filter(KeywordMapping.project_id == project.id, KeywordMapping.is_archived == False)  # noqa: E712
        .all()
    )
    approvals = db.query(Approval).filter(Approval.project_id == project.id).all()
    briefs = db.query(ContentBrief).filter(ContentBrief.project_id == project.id).all()

    pending_approvals = [a for a in approvals if a.status == "PENDING"]
    waiting_reqs = [r for r in reqs if r.status in ("WAITING_USER", "MAPPING_REQUIRED")]
    imported_reqs = [r for r in reqs if r.status == "IMPORTED"]

    step_map = {s.step_number: s for s in steps}

    # Step 1
    has_topic = bool(
        (project.topic_pillar_code or project.topic_pillar_name or project.main_topic)
        and (project.primary_keyword_original or project.primary_keyword_current)
    )
    if has_topic:
        step_map[1].status = "QUALITY_APPROVED" if (project.business_goal and project.target_audience) else "PROCESS_COMPLETED"
        step_map[1].summary = f"{project.topic_pillar_code or project.code}: {project.primary_keyword_current or project.primary_keyword_original}"
    else:
        step_map[1].status = "READY"
        step_map[1].summary = "Cần nhập Topic Pillar & keyword chính từ Excel/CSV hoặc form."

    # Step 2
    if dgs:
        uncertain_dgs = [d for d in dgs if d.status == "UNCERTAIN"]
        step_map[2].status = "REVIEW_REQUIRED" if uncertain_dgs else "PROCESS_COMPLETED"
        step_map[2].summary = (
            f"{len(dgs)} nhóm nhu cầu ({len(uncertain_dgs)} nhóm UNCERTAIN cần kiểm tra nguồn)."
            if uncertain_dgs
            else f"{len(dgs)} nhóm nhu cầu đã được AI phân tích & lưu SQLite."
        )
    elif has_topic:
        step_map[2].status = "READY"
        step_map[2].summary = "Sẵn sàng chạy AI Topic Analyst & Critic."
    else:
        step_map[2].status = "NOT_STARTED"
        step_map[2].summary = ""

    # Step 3
    if reqs:
        if waiting_reqs:
            step_map[3].status = "WAITING_USER"
            step_map[3].summary = f"Có {len(waiting_reqs)}/{len(reqs)} phiếu Semrush đang chờ bạn xuất file."
        else:
            step_map[3].status = "PROCESS_COMPLETED"
            step_map[3].summary = f"Đã hoàn tất nhận file cho {len(imported_reqs)}/{len(reqs)} phiếu."
    elif dgs:
        step_map[3].status = "READY"
        step_map[3].summary = "Tạo phiếu Yêu cầu Semrush từ các nhóm nhu cầu đã chọn."
    else:
        step_map[3].status = "NOT_STARTED"
        step_map[3].summary = ""

    # Step 4
    if batches:
        step_map[4].status = "PROCESS_COMPLETED"
        step_map[4].summary = (
            f"Đã xác nhận {len(batches)} batch ({summary['metrics_rows_count']} metrics đúng thị trường, "
            f"{summary['organic_rows_count']} organic hợp lệ)."
        )
    elif reqs:
        step_map[4].status = "WAITING_USER"
        step_map[4].summary = "Chờ tải file CSV/XLSX xuất từ Semrush và xác nhận ghép cột."
    else:
        step_map[4].status = "NOT_STARTED"
        step_map[4].summary = ""

    # Step 5
    if critiques_post:
        last_c = critiques_post[-1]
        step_map[5].status = (
            "REVIEW_REQUIRED"
            if last_c.decision_status in ("REVIEW_REQUIRED", "WAITING_USER", "HOLD")
            else "PROCESS_COMPLETED"
        )
        step_map[5].summary = f"Đã chạy {len(critiques_post)} lượt Critic sau Semrush (chu kỳ #{project.research_cycle})."
    elif batches:
        step_map[5].status = "READY"
        step_map[5].summary = "Đã có dữ liệu Semrush — sẵn sàng kiểm tra Quality Gates & chạy AI Critic."
    else:
        step_map[5].status = "NOT_STARTED"
        step_map[5].summary = ""

    # Step 6
    eligible_count = summary["eligible_official_count"]
    stale_approval_count = sum(1 for d in elig_map.values() if d["approval_state"] == "STALE_SUPERSEDED")
    if mappings:
        if eligible_count == len(mappings) and not pending_approvals:
            step_map[6].status = "QUALITY_APPROVED"
            step_map[6].summary = f"{eligible_count}/{len(mappings)} mapping đạt đủ Quality Gates & phê duyệt."
        elif pending_approvals or stale_approval_count > 0:
            step_map[6].status = "HOLD"
            step_map[6].summary = (
                f"{eligible_count}/{len(mappings)} mapping đủ điều kiện chính thức · "
                f"{len(pending_approvals)} mục chờ phê duyệt."
            )
        else:
            step_map[6].status = "REVIEW_REQUIRED"
            step_map[6].summary = f"{eligible_count}/{len(mappings)} mapping đủ điều kiện chính thức ({summary['serp_status']})."
    elif batches:
        step_map[6].status = "READY"
        step_map[6].summary = "Sẵn sàng lập kế hoạch bài viết & Keyword Mapping dự thảo."
    else:
        step_map[6].status = "NOT_STARTED"
        step_map[6].summary = ""

    # Step 7 (live freshness projection, not merely persisted columns!)
    mappings_by_id = {m.id: m for m in mappings}
    brief_freshness = [
        (
            b,
            compute_effective_brief_freshness(
                b,
                mappings_by_id.get(b.keyword_mapping_id) if b.keyword_mapping_id else None,
                elig_map.get(b.keyword_mapping_id) if b.keyword_mapping_id else None,
            ),
        )
        for b in briefs
    ]
    official_fresh_briefs = [b for b, f in brief_freshness if f["effective_brief_mode"] == "OFFICIAL" and not f["effective_is_stale"]]
    stale_briefs = [b for b, f in brief_freshness if f["effective_is_stale"]]
    if official_fresh_briefs and not stale_briefs:
        step_map[7].status = "QUALITY_APPROVED"
        step_map[7].summary = f"{len(official_fresh_briefs)} Content Brief CHÍNH THỨC sẵn sàng xuất."
    elif stale_briefs:
        step_map[7].status = "REVIEW_REQUIRED"
        step_map[7].summary = f"Có {len(stale_briefs)} Content Brief đã cũ do Mapping/Evidence thay đổi — cần duyệt và tạo lại."
    elif briefs:
        step_map[7].status = "PROCESS_COMPLETED"
        step_map[7].summary = f"{len(briefs)} Content Brief DỰ THẢO ({summary['serp_status']})."
    elif mappings:
        step_map[7].status = "READY"
        step_map[7].summary = (
            f"Có {eligible_count}/{len(mappings)} mapping đủ điều kiện tạo Brief CHÍNH THỨC."
            if eligible_count > 0
            else "Chưa có mapping nào đủ điều kiện chính thức — chỉ có thể tạo Brief DỰ THẢO."
        )
    else:
        step_map[7].status = "NOT_STARTED"
        step_map[7].summary = ""

    blockers: list[dict[str, Any]] = []
    if not has_topic:
        blockers.append(
            {
                "code": "TOPIC_NOT_CONFIGURED",
                "severity": "ERROR",
                "title": "Chưa thiết lập Topic Pillar & Keyword chính",
                "cause": "Dự án chưa có dữ liệu nguồn tối thiểu trong SQLite.",
                "impact": "Chưa thể chạy AI phân tích nhu cầu và tạo phiếu Semrush.",
                "solution": "Tải file XLSX/CSV taxonomy hoặc nhập trực tiếp tại Bước 01.",
                "cta_label": "Mở Bước 01",
                "cta_href": "/steps/01-topic",
            }
        )
    if summary["missing_kd_count"] > 0:
        blockers.append(
            {
                "code": "KD_MISSING",
                "severity": "WARNING",
                "title": f"{summary['missing_kd_count']} keyword thiếu chỉ số KD",
                "cause": "File Semrush đã import thiếu cột Keyword Difficulty hoặc giá trị bị trống.",
                "impact": "Các mapping thiếu KD bị chặn tạo Brief CHÍNH THỨC (vẫn xem được Volume & tạo Brief DỰ THẢO).",
                "solution": "Xuất lại báo cáo Keyword Overview có cột KD từ Semrush và tải bổ sung.",
                "cta_label": "Mở Yêu cầu Semrush",
                "cta_href": "/steps/03-semrush",
            }
        )
    if summary["metrics_rows_count"] > 0 and summary["serp_status"] in ("SERP_NOT_VERIFIED", "PARTIAL_SERP_EVIDENCE"):
        blockers.append(
            {
                "code": summary["serp_status"],
                "severity": "WARNING",
                "title": (
                    "Chưa có bằng chứng SERP đầy đủ theo từng từ khóa"
                    if summary["serp_status"] == "SERP_NOT_VERIFIED"
                    else "Bằng chứng SERP mới đạt một phần (PARTIAL_SERP_EVIDENCE)"
                ),
                "cause": "Chưa đủ >= 3 URL organic hợp lệ cho từng từ khóa chính trong cùng thị trường.",
                "impact": "Các mapping thiếu SERP chỉ ở chế độ DỰ THẢO, không được xuất Content Brief CHÍNH THỨC.",
                "solution": "Xuất báo cáo SERP Analysis / ORGANIC_RESULTS từ Semrush cho đúng từ khóa và tải lên Bước 04.",
                "cta_label": "Mở Bước 04",
                "cta_href": "/steps/04-upload",
            }
        )
    if pending_approvals:
        blockers.append(
            {
                "code": "PENDING_HUMAN_APPROVAL",
                "severity": "WARNING",
                "title": f"{len(pending_approvals)} quyết định SEO đang chờ phê duyệt",
                "cause": "AI và engine chỉ đề xuất; người dùng phải duyệt đúng phiên bản/fingerprint hiện hành.",
                "impact": "Gate F6 đang ở trạng thái HOLD nên chưa thể xuất Content Brief CHÍNH THỨC cho các mục chờ duyệt.",
                "solution": "Mở màn hình Chờ phê duyệt để duyệt, từ chối hoặc yêu cầu bổ sung bằng chứng.",
                "cta_label": "Mở Chờ phê duyệt",
                "cta_href": "/approvals",
            }
        )
    if stale_briefs:
        blockers.append(
            {
                "code": "BRIEF_STALE_NEEDS_REGENERATION",
                "severity": "WARNING",
                "title": f"{len(stale_briefs)} Content Brief đã cũ do thay đổi Mapping/Evidence",
                "cause": "Dữ liệu Mapping hoặc bằng chứng đã cập nhật lên phiên bản mới hơn bản dùng khi sinh Brief.",
                "impact": "Brief cũ tự động bị hạ xuống DRAFT (STALE) để tránh dùng tài liệu lỗi thời.",
                "solution": "Phê duyệt lại phiên bản Mapping mới rồi tạo lại Content Brief ở Bước 07.",
                "cta_label": "Mở Bước 07",
                "cta_href": "/steps/07-brief",
            }
        )

    if not has_topic:
        next_action = {
            "title": "Thiết lập Topic Pillar & Keyword nguồn",
            "description": "Tải file XLSX/CSV hoặc nhập trực tiếp Topic Pillar, mã nội dung và keyword chính tại Bước 01.",
            "cta_label": "Đi tới Bước 01",
            "cta_href": "/steps/01-topic",
        }
    elif not dgs:
        next_action = {
            "title": "Chạy AI phân tích Bản đồ nhu cầu",
            "description": "AI Topic Analyst và Critic sẽ nhóm nhu cầu thực sự của người tìm kiếm và kiểm tra ranh giới Topic Pillar.",
            "cta_label": "Đi tới Bước 02",
            "cta_href": "/steps/02-demand-map",
        }
    elif not reqs:
        next_action = {
            "title": "Tạo phiếu Yêu cầu Semrush",
            "description": "Sinh danh sách báo cáo Semrush thật sự cần lấy kèm hướng dẫn thao tác từng bước.",
            "cta_label": "Đi tới Bước 03",
            "cta_href": "/steps/03-semrush",
        }
    elif not batches:
        next_action = {
            "title": "Upload CSV/XLSX từ Semrush & ghép cột",
            "description": "Tải file bạn vừa xuất trên Semrush UI, kiểm tra preview và xác nhận lưu Evidence vào SQLite.",
            "cta_label": "Đi tới Bước 04",
            "cta_href": "/steps/04-upload",
        }
    elif not critiques_post:
        next_action = {
            "title": "Kiểm tra Quality Gates & chạy AI Critic sau Semrush",
            "description": "Đối chiếu dữ liệu Semrush thực tế với giả thuyết ban đầu để xác định điểm thiếu bằng chứng.",
            "cta_label": "Đi tới Bước 05",
            "cta_href": "/steps/05-evidence",
        }
    elif not mappings:
        next_action = {
            "title": "Lập Kế hoạch bài viết & Keyword Mapping",
            "description": "Xây dựng cơ hội bài viết dựa trên bằng chứng, tách rõ ARTICLE và TOOL/DOWNLOAD.",
            "cta_label": "Đi tới Bước 06",
            "cta_href": "/steps/06-mapping",
        }
    elif pending_approvals:
        next_action = {
            "title": f"Phê duyệt {len(pending_approvals)} đề xuất SEO quan trọng",
            "description": "Rà soát phiên bản Mapping, giá trị gốc, đề xuất mới và bằng chứng trước khi tạo Content Brief chính thức.",
            "cta_label": "Mở Chờ phê duyệt",
            "cta_href": "/approvals",
        }
    else:
        next_action = {
            "title": "Tạo & Xuất SEO Content Brief",
            "description": "Sinh Content Brief đầy đủ 3 bảng logic + Writing Strategy cấp toàn bài và xuất XLSX/CSV/JSON/HTML.",
            "cta_label": "Đi tới Bước 07",
            "cta_href": "/steps/07-brief",
        }

    db.commit()

    step_hrefs = {num: href for num, _, _, href in STEP_SPECS}
    return {
        "steps": [
            {
                "step_number": s.step_number,
                "step_key": s.step_key,
                "title": s.title,
                "status": s.status,
                "summary": s.summary,
                "href": step_hrefs[s.step_number],
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in steps
        ],
        "counts": {
            "demand_groups": len(dgs),
            "research_requests": len(reqs),
            "waiting_requests": len(waiting_reqs),
            "research_batches": len(batches),
            "pending_approvals": len(pending_approvals),
            "keyword_mappings": len(mappings),
            "eligible_official_mappings": eligible_count,
            "content_briefs": len(briefs),
        },
        "gates": gate_eval["gates"],
        "evidence_summary": summary,
        "blockers": blockers,
        "next_action": next_action,
    }

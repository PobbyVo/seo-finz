from __future__ import annotations

import time
from typing import Any

from app.ai.adapters.base import (
    AIProviderAdapter,
    ProviderConfig,
    StructuredGenerationResult,
    TestConnectionResult,
)


from app.domain.research_business import infer_query_asset as _guess_page_type


class MockAdapter(AIProviderAdapter):
    """
    Deterministic zero-cost local mock provider for safe development & automated tests.
    Never invents Volume/KD metrics and dynamically derives output from the active project's
    SQLite taxonomy/keywords/evidence (never hardcoded to a single demo topic).
    """

    provider_name = "mock"

    def test_connection(self, config: ProviderConfig) -> TestConnectionResult:
        started = time.perf_counter()
        model = config.model_id or "finz-mock-deterministic-v1"
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return TestConnectionResult(
            ok=True,
            provider=self.provider_name,
            requested_model=model,
            actual_model=model,
            latency_ms=latency_ms,
            status="CONNECTED",
            message=f"Mock Provider hoạt động nội bộ (0 chi phí API) — model {model}.",
        )

    def generate_structured_output(
        self,
        config: ProviderConfig,
        system_prompt: str,
        user_prompt: str,
        context: dict[str, Any] | None = None,
    ) -> StructuredGenerationResult:
        started = time.perf_counter()
        ctx = context or {}
        task = ctx.get("task", "ANALYST")
        model = config.model_id or "finz-mock-deterministic-v1"

        if task == "BRIEF_WRITER":
            from app.domain.brief_writer import mock_brief
            data = mock_brief(ctx)
        elif task == "SERP_ANALYST":
            from app.domain.semrush_parser import infer_page_type_from_url
            data = {"rows": [{"evidence_id": row["id"], "page_type": infer_page_type_from_url(row.get("url"),row.get("title")), "rationale": "Giả thuyết offline từ URL/title; chưa đọc trang.", "source_refs": [row["id"]]} for row in ctx.get("evidence_rows", [])], "intent": "Chưa xác minh", "mandatory_ideas": [], "gaps": [], "length_reference": "Không đọc được trong Mock", "legal_sources_needed": []}
        elif task == "ANALYST":
            data = self._mock_analyst(ctx)
        elif task == "CRITIC_PRE":
            data = self._mock_critic_pre(ctx)
        elif task == "CRITIC_POST":
            data = self._mock_critic_post(ctx)
        else:
            data = {"ok": True, "summary": "Mock response"}

        latency_ms = max(2, int((time.perf_counter() - started) * 1000))
        return StructuredGenerationResult(
            ok=True,
            provider=self.provider_name,
            requested_model=model,
            actual_model=model,
            latency_ms=latency_ms,
            data=data,
        )

    def _mock_analyst(self, ctx: dict[str, Any]) -> dict[str, Any]:
        sources = ctx.get("source_keywords", [])
        primaries = [r for r in sources if r.get("role") == "PRIMARY"]
        if len(primaries) > 1:
            results = [self._mock_analyst({**ctx, "source_keywords":[], "primary_keyword":row["keyword"], "content_code":row["content_code"], "content_title":row.get("content_title",""), "secondary_keywords":[r["keyword"] for r in sources if r.get("content_code")==row["content_code"] and r.get("role")!="PRIMARY"]}) for row in primaries]
            return {"summary":f"Phân tích offline {len(primaries)} mã nội dung trong chủ đề; các giả thuyết cần Semrush và người duyệt.", **{key:[item for result in results for item in result.get(key,[])] for key in ("demand_groups","proposed_candidates","recommended_requests")}}
        topic_name = ctx.get("topic_pillar_name") or ctx.get("main_topic") or ctx.get("project_name") or "Chủ đề nghiên cứu"
        topic_code = ctx.get("topic_pillar_code") or ctx.get("project_code") or "TOPIC"
        primary_kw = ctx.get("primary_keyword") or topic_name.lower()
        secondary_kws: list[str] = list(ctx.get("secondary_keywords") or [])
        valid_refs: list[str] = list(ctx.get("valid_source_refs") or [])
        base_ref = valid_refs[0] if valid_refs else f"TOPIC:{topic_code}"
        business_goal = ctx.get("business_goal") or ""
        audience = ctx.get("target_audience") or ""

        primary_page_type = _guess_page_type(primary_kw)

        groups: list[dict[str, Any]] = [
            {
                "name": f"Nhu cầu cốt lõi: {topic_name}",
                "user_need": f"Người tìm kiếm muốn hiểu bản chất, quy tắc áp dụng và cách triển khai đúng về '{primary_kw}'"
                + (f" (đối tượng: {audience})" if audience else "")
                + ".",
                "coverage_type": "COVERED",
                "assumed_page_type": primary_page_type,
                "assumed_intent": "Informational / Problem-solving (giả định, chưa kiểm chứng SERP)",
                "seed_keywords": [primary_kw],
                "related_keywords": secondary_kws[:6],
                "supporting_evidence": [
                    f"Gắn trực tiếp với Topic Pillar {topic_code} ({topic_name}) và keyword chính gốc '{primary_kw}'.",
                    f"Liên kết mục tiêu kinh doanh: {business_goal or 'Chưa khai báo — cần bổ sung để ưu tiên chính xác.'}",
                ],
                "source_refs": [base_ref],
                "strongest_counterargument": (
                    f"Chưa có dữ liệu Semrush (Volume/KD/Intent) và chưa có ORGANIC_RESULTS để khẳng định '{primary_kw}' "
                    "nên gom chung hay tách khỏi các biến thể phụ."
                ),
                "missing_data": [
                    "Volume, KD và Intent từ báo cáo Keyword Overview trên Semrush.",
                    "Danh sách từ khóa liên quan (Related) để phát hiện biến thể đồng nghĩa.",
                ],
                "next_action": f"Xuất báo cáo KEYWORD_OVERVIEW trên Semrush cho seed '{primary_kw}'.",
                "recommended_semrush_report": "KEYWORD_OVERVIEW",
                "boundary_note": f"Thuộc phạm vi {topic_code}; cần đối chiếu không lấn sang Pillar khác.",
                "business_relevance_note": (
                    f"Phục vụ mục tiêu '{business_goal}' — giữ lại đánh giá ngay cả khi Volume thấp."
                    if business_goal
                    else "Cần xác nhận mức độ đóng góp kinh doanh với stakeholder."
                ),
                "status": "RESEARCH_CANDIDATE",
            },
            {
                "name": f"Câu hỏi thực tế & tình huống áp dụng ({topic_name})",
                "user_need": f"Người đọc gặp vướng mắc cụ thể trong thực tế xoay quanh '{primary_kw}' và cần lời giải từng bước kèm ví dụ.",
                "coverage_type": "GAP",
                "assumed_page_type": "ARTICLE",
                "assumed_intent": "Informational — Question-based (giả định, chưa kiểm chứng SERP)",
                "seed_keywords": [f"cách xử lý {primary_kw}", f"quy định {primary_kw}"],
                "related_keywords": secondary_kws[6:10] if len(secondary_kws) > 6 else [f"lưu ý khi làm {primary_kw}"],
                "supporting_evidence": [
                    f"Phát triển từ mã nguồn {base_ref} nhằm lấp khoảng trống câu hỏi dài đuôi (long-tail B2B/chuyên môn).",
                ],
                "source_refs": [base_ref],
                "strongest_counterargument": (
                    "Các câu hỏi này có thể bị trùng ý định tìm kiếm với bài trụ cột nếu Google ưu tiên bài tổng hợp dài."
                ),
                "missing_data": [
                    "Báo cáo Questions trên Semrush để kiểm chứng các câu hỏi thực tế người dùng tìm.",
                    "Bằng chứng SERP (ORGANIC_RESULTS) nếu muốn tách bài riêng.",
                ],
                "next_action": f"Xuất báo cáo QUESTIONS trên Semrush cho seed '{primary_kw}'.",
                "recommended_semrush_report": "QUESTIONS",
                "boundary_note": f"Nằm trong trục chia của {topic_code}; tránh mở rộng sang quy trình pháp lý ngoài phạm vi.",
                "business_relevance_note": "Nhóm câu hỏi chuyên sâu thường có Volume nhỏ nhưng tỷ lệ chuyển đổi B2B cao.",
                "status": "RESEARCH_CANDIDATE",
            },
        ]

        # Detect if any secondary keyword clearly implies a TOOL or DOWNLOAD asset
        tool_kws = [k for k in secondary_kws if _guess_page_type(k) in ("TOOL", "DOWNLOAD")]
        if tool_kws:
            tk = tool_kws[0]
            t_type = _guess_page_type(tk)
            groups.append(
                {
                    "name": f"Tài nguyên/Công cụ thực hành: {tk}",
                    "user_need": f"Người tìm kiếm muốn dùng ngay công cụ hoặc tải mẫu sẵn thay vì chỉ đọc bài lý thuyết ({tk}).",
                    "coverage_type": "OVERLAP",
                    "assumed_page_type": t_type,
                    "assumed_intent": "Transactional / Utility (giả định, chưa kiểm chứng SERP)",
                    "seed_keywords": [tk],
                    "related_keywords": tool_kws[1:4],
                    "supporting_evidence": [
                        f"Xuất hiện trực tiếp trong danh sách keyword nguồn thuộc {base_ref}.",
                        f"Cần phân loại {t_type}, KHÔNG tính vào quota 5–7 bài ARTICLE.",
                    ],
                    "source_refs": [base_ref],
                    "strongest_counterargument": "Cần kiểm chứng trên Semrush xem người tìm kiếm thực sự muốn trang công cụ/tải mẫu hay bài hướng dẫn.",
                    "missing_data": ["Báo cáo KEYWORD_OVERVIEW và ORGANIC_RESULTS (nếu có) để xác định dạng trang."],
                    "next_action": f"Xuất KEYWORD_OVERVIEW cho '{tk}' để kiểm chứng nhu cầu {t_type}.",
                    "recommended_semrush_report": "KEYWORD_OVERVIEW",
                    "boundary_note": f"Thuộc {topic_code} nhưng là dạng {t_type}, tách biệt với bài ARTICLE.",
                    "business_relevance_note": "Công cụ/biểu mẫu có thể làm lead magnet rất tốt cho mục tiêu chuyển đổi.",
                    "status": "RESEARCH_CANDIDATE",
                }
            )

        return {
            "summary": f"Đã phân tích {topic_code} ({topic_name}) thành {len(groups)} nhóm nhu cầu giả thuyết. Chưa có Volume/KD/SERP xác minh.",
            "demand_groups": groups,
            "proposed_candidates": [
                {
                    "keyword": f"hướng dẫn {primary_kw} chi tiết",
                    "candidate_type": "EXPANSION",
                    "assumed_page_type": "ARTICLE",
                    "source_refs": [base_ref],
                    "rationale": f"Mở rộng tự nhiên từ keyword gốc '{primary_kw}' để kiểm chứng nhu cầu hướng dẫn từng bước trên Semrush.",
                }
            ],
            "recommended_requests": [
                {
                    "seed_keyword": primary_kw,
                    "report_type": "KEYWORD_OVERVIEW",
                    "purpose": "Lấy bằng chứng Volume, KD, Intent và SERP Features cho từ khóa chính và biến thể.",
                },
                {
                    "seed_keyword": primary_kw,
                    "report_type": "QUESTIONS",
                    "purpose": "Kiểm chứng câu hỏi thực tế của người tìm kiếm để quyết định gộp hay tách bài.",
                },
            ],
        }

    def _mock_critic_pre(self, ctx: dict[str, Any]) -> dict[str, Any]:
        primary_kw = ctx.get("primary_keyword") or "từ khóa chính"
        groups = ctx.get("demand_groups") or []
        return {
            "supporting_evidence": [
                f"Các nhóm nhu cầu đều bám theo nguồn taxonomy đã lưu cho '{primary_kw}'.",
                "Chưa bịa đặt chỉ số Volume, KD hay giả định đã kiểm tra SERP Top 10.",
            ],
            "counterarguments": [
                "Search Intent hiện tại mới là suy luận từ ngôn ngữ, chưa có xác nhận từ dữ liệu Semrush.",
                f"Đang có {len(groups)} nhóm nhu cầu: cần tránh tách từ đồng nghĩa thành hai bài riêng nếu chưa có bằng chứng khác biệt.",
            ],
            "missing_data": [
                "Chỉ số Volume, KD, Intent từ Semrush (KEYWORD_OVERVIEW / RELATED).",
                "Bằng chứng trang xếp hạng thực tế (ORGANIC_RESULTS) nếu cần chốt gộp/tách bài.",
            ],
            "changes_from_evidence": [],
            "followup_requests": [
                {
                    "seed_keyword": primary_kw,
                    "report_type": "RELATED",
                    "purpose": "Phát hiện từ khóa đồng nghĩa và nhóm nhu cầu giao thoa trước khi lập Keyword Mapping.",
                }
            ],
            "next_action": "Tạo và thực hiện các phiếu Yêu cầu Semrush tại Bước 03, sau đó tải file CSV/XLSX ở Bước 04.",
            "decision_status": "WAITING_USER",
        }

    def _mock_critic_post(self, ctx: dict[str, Any]) -> dict[str, Any]:
        primary_kw = ctx.get("primary_keyword") or "từ khóa chính"
        metrics_count = int(ctx.get("metrics_rows_count") or 0)
        organic_count = int(ctx.get("organic_rows_count") or 0)
        missing_kd = int(ctx.get("missing_kd_count") or 0)
        missing_intent = int(ctx.get("missing_intent_count") or 0)
        low_vol_relevant = list(ctx.get("low_volume_keywords") or [])

        supporting = [
            f"Đã ghi nhận {metrics_count} dòng bằng chứng chỉ số Semrush vào SQLite.",
        ]
        if organic_count > 0:
            supporting.append(f"Đã có {organic_count} dòng dữ liệu ORGANIC_RESULTS giúp kiểm chứng dạng trang thực tế.")
        if low_vol_relevant:
            supporting.append(
                f"Phát hiện {len(low_vol_relevant)} từ khóa Volume thấp ({', '.join(low_vol_relevant[:3])}) vẫn được giữ để đánh giá theo giá trị kinh doanh, không loại bằng ngưỡng cứng."
            )

        counterarguments: list[str] = []
        missing: list[str] = []
        followups: list[dict[str, str]] = []

        if missing_kd > 0:
            counterarguments.append(f"Có {missing_kd} từ khóa thiếu KD — không thể kết luận độ cạnh tranh chỉ từ Volume.")
            missing.append(f"Thiếu chỉ số KD ở {missing_kd} từ khóa.")
            followups.append(
                {
                    "seed_keyword": primary_kw,
                    "report_type": "KEYWORD_OVERVIEW",
                    "purpose": "Bổ sung cột KD (Keyword Difficulty) bị thiếu cho bộ từ khóa nguồn.",
                }
            )
        if missing_intent > 0:
            counterarguments.append(f"Có {missing_intent} từ khóa thiếu Intent từ Semrush.")
            missing.append(f"Thiếu cột Intent ở {missing_intent} từ khóa.")
        if organic_count == 0:
            counterarguments.append(
                "Chưa có file ORGANIC_RESULTS nên trạng thái SERP phải giữ SERP_NOT_VERIFIED; chỉ được lập kế hoạch dự thảo, không đóng dấu đã xác minh."
            )
            missing.append("Báo cáo ORGANIC_RESULTS từ Semrush (nếu gói tài khoản hỗ trợ xuất) để xác minh dạng trang và gộp/tách bài.")
            followups.append(
                {
                    "seed_keyword": primary_kw,
                    "report_type": "ORGANIC_RESULTS",
                    "purpose": "Xác minh URL/loại trang đang xếp hạng thực tế để quyết định gộp hay tách bài.",
                }
            )
        if not counterarguments:
            counterarguments.append(
                "Dù đã có metrics và dữ liệu organic, vẫn cần chuyên viên SEO phê duyệt cuối cùng về ưu tiên kinh doanh trước khi xuất Content Brief chính thức."
            )

        changes = [
            "Cập nhật nhận định từ giả thuyết thuần túy sang đối chiếu bằng chứng thực tế trong SQLite.",
            "Bảo lưu yêu cầu không tự nâng READY_FOR_BRIEF chỉ từ Volume và KD.",
        ]

        decision = "REVIEW_REQUIRED" if (missing_kd > 0 or metrics_count == 0) else "PROCESS_COMPLETED"
        next_action = (
            "Duyệt các yêu cầu nghiên cứu bổ sung để lấy đủ bằng chứng, hoặc sang Bước 06 lập kế hoạch dự thảo (ghi rõ SERP_NOT_VERIFIED)."
            if organic_count == 0 or missing_kd > 0
            else "Đủ bằng chứng cơ bản để lập Keyword Mapping tại Bước 06 và gửi Chờ phê duyệt."
        )

        return {
            "supporting_evidence": supporting,
            "counterarguments": counterarguments,
            "missing_data": missing,
            "changes_from_evidence": changes,
            "followup_requests": followups,
            "next_action": next_action,
            "decision_status": decision,
        }

"use client";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";

type Row = {
  backlog_label: string;
  review_notes: string;
  mapping_id: string;
  article_code: string;
  keyword: string;
  page_type: string;
  priority: string;
  url: string;
  content_code: string;
  content_title: string;
  funnel_stage: string;
  priority_reason: string;
  approval_status: string;
  verified_secondary: Array<{ keyword: string; volume: number; kd: number }>;
  suggested_questions: string[];
  analysis: {
    distribution?: Record<string, number>;
    decision?: string;
    analysis?: {
      mandatory_ideas?: string[];
      gaps?: string[];
      length_reference?: string;
      rows?: Array<{
        evidence_id: string;
        page_type: string;
        rationale: string;
      }>;
    };
  };
};
export function ResearchHandoff({ projectId }: { projectId: string }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [message, setMessage] = useState("");
  const load = () =>
    apiRequest<{ rows: Row[] }>(
      `/api/v1/projects/${projectId}/research-handoff`,
    )
      .then((r) => setRows(r.rows))
      .catch((e) => setMessage(e.message));
  useEffect(() => {
    void load();
  }, [projectId]);
  return (
    <section className="space-y-3">
      <h2 className="font-bold">Bàn giao nghiên cứu theo chủ đề</h2>
      <button className="finz-v2-secondary" onClick={() => void load()}>
        Cập nhật bảng bàn giao
      </button>
      <p role="status">{message}</p>
      {rows.map((row) => (
        <details
          key={row.mapping_id}
          className="rounded-xl border border-slate-700 p-4"
        >
          <summary>
            {row.article_code} · {row.keyword} · {row.backlog_label} ·{" "}
            {row.priority} · {row.approval_status}
          </summary>
          <dl className="grid gap-2 mt-3 text-sm">
            <dt>Mã nội dung gốc / giai đoạn</dt>
            <dd>
              {row.content_code} · {row.funnel_stage || "Chưa khai báo"}
            </dd>
            <dt>Góc bài</dt>
            <dd>{row.content_title || "Cần bổ sung"}</dd>
            <dt>Lý do ưu tiên</dt>
            <dd>{row.priority_reason}</dd>
            <dt>Keyword phụ có số</dt>
            <dd>
              {row.verified_secondary
                .map((k) => `${k.keyword}: Volume ${k.volume}, KD ${k.kd}`)
                .join("; ") || "Chưa có bằng chứng"}
            </dd>
            <dt>Câu hỏi gợi ý — chưa xác minh</dt>
            <dd>{row.suggested_questions.join("; ") || "Chưa có"}</dd>
            <dt>Phân bố loại trang top 10</dt>
            <dd>
              {Object.entries(row.analysis.distribution || {})
                .map(([k, v]) => `${k}: ${v}/10`)
                .join("; ") || "Chưa xác minh"}
            </dd>
            <dt>Ý bắt buộc</dt>
            <dd>
              {row.analysis.analysis?.mandatory_ideas?.join("; ") ||
                "Chưa đủ bài đã đọc"}
            </dd>
            <dt>Khoảng trống</dt>
            <dd>
              {row.analysis.analysis?.gaps?.join("; ") || "Chưa đủ bằng chứng"}
            </dd>
            <dt>Độ dài tham khảo</dt>
            <dd>
              {row.analysis.analysis?.length_reference ||
                "Không đọc được / chưa đọc"}
            </dd>
            <dt>Ghi chú duyệt / yêu cầu sửa</dt>
            <dd>{row.review_notes || "Chưa có"}</dd>
            <dt>URL dự kiến</dt>
            <dd>{row.url}</dd>
          </dl>
          <form
            className="mt-3 flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = e.currentTarget;
              const note = String(new FormData(form).get("note") || "");
              try {
                await apiRequest(
                  `/api/v1/projects/${projectId}/mapping/${row.mapping_id}/reprocess`,
                  { method: "POST", body: JSON.stringify({ note }) },
                );
                await load();
                setMessage(
                  "Đã chạy lại F5/F6 riêng dòng. Xem phê duyệt phiên bản hiện hành.",
                );
              } catch (error) {
                setMessage(
                  error instanceof Error
                    ? error.message
                    : "Không chạy lại được dòng.",
                );
              }
            }}
          >
            <input
              className="finz-v2-input"
              name="note"
              aria-label="Ghi chú sửa dòng mapping"
              placeholder="Ghi chú sửa dòng"
            />
            <button className="finz-v2-secondary" type="submit">
              Sửa · chạy lại F5/F6
            </button>
          </form>
          {row.analysis.analysis?.rows?.map((label) => (
            <label key={label.evidence_id} className="block mt-2 text-xs">
              {label.rationale}
              <select
                className="finz-v2-input"
                defaultValue={label.page_type}
                aria-label="Sửa loại trang SERP"
                onChange={async (e) => {
                  try {
                    await apiRequest(
                      `/api/v1/projects/${projectId}/serp-labels/${label.evidence_id}`,
                      {
                        method: "PUT",
                        body: JSON.stringify({ page_type: e.target.value }),
                      },
                    );
                    setMessage(
                      "Đã lưu nhãn. Chạy lại phân tích SERP và mapping để người duyệt xem phiên bản mới.",
                    );
                  } catch (error) {
                    setMessage(
                      error instanceof Error
                        ? error.message
                        : "Không lưu được nhãn.",
                    );
                  }
                }}
              >
                {[
                  "ARTICLE",
                  "TOOL",
                  "DOWNLOAD",
                  "SERVICE",
                  "PRODUCT",
                  "DATA",
                  "UNKNOWN",
                ].map((kind) => (
                  <option key={kind}>{kind}</option>
                ))}
              </select>
            </label>
          ))}
        </details>
      ))}
    </section>
  );
}

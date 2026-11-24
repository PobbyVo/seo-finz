"use client";
import { useState, useEffect } from "react";
import { apiRequest } from "@/lib/api";
type Data = {
  source_keywords: Array<{
    keyword: string;
    volume: number | null;
    included: boolean;
    reason: string;
  }>;
  candidates: Array<{
    id: string;
    keyword: string;
    rationale: string;
    status: string;
    volume: number | null;
  }>;
  notice: string;
};
export function KeywordExpansion({ projectId }: { projectId: string }) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const load = () =>
    apiRequest<Data>(`/api/v1/projects/${projectId}/keyword-expansion`)
      .then(setData)
      .catch((e) => setError(e.message));
  useEffect(() => {
    void load();
  }, [projectId]);
  return (
    <section className="rounded-xl border border-slate-700 p-4 space-y-3">
      <h2 className="font-bold">Mở rộng nghiên cứu hướng tới 5–7 bài</h2>
      <p className="text-sm text-slate-300">
        Keyword thiếu Volume hoặc Volume 0 được loại khỏi kế hoạch, vẫn giữ dữ
        liệu nguồn. Keyword mới chờ bạn kiểm tra Semrush và duyệt trước khi
        thành bài viết.
      </p>
      <button
        className="finz-v2-primary"
        onClick={async () => {
          try {
            setData(
              await apiRequest<Data>(
                `/api/v1/projects/${projectId}/keyword-expansion`,
                { method: "POST" },
              ),
            );
            setError(
              "Đã cập nhật bộ lọc và phiếu Semrush. Chạy lại mapping/brief để dùng bộ keyword mới.",
            );
          } catch (e) {
            setError(
              e instanceof Error ? e.message : "Không tạo được đề xuất.",
            );
          }
        }}
      >
        Lọc Volume và tạo đề xuất Semrush
      </button>
      <p role="status">{error}</p>
      {data && (
        <>
          <details>
            <summary>
              Keyword chưa đủ điều kiện (
              {data.source_keywords.filter((k) => !k.included).length})
            </summary>
            {data.source_keywords
              .filter((k) => !k.included)
              .map((k) => (
                <p key={k.keyword} className="text-sm">
                  {k.keyword} — {k.reason}
                </p>
              ))}
          </details>
          <textarea
            className="finz-v2-input w-full"
            aria-label="Keyword cần kiểm tra trong Semrush"
            readOnly
            rows={8}
            value={data.candidates.map((c) => c.keyword).join("\n")}
          />
          {data.candidates.map((c) => (
            <details key={c.id}>
              <summary>
                {c.keyword} — {c.status}
              </summary>
              <p className="text-sm">{c.rationale}</p>
            </details>
          ))}
          <p className="text-sm">{data.notice}</p>
        </>
      )}
    </section>
  );
}

'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowDownToLine, FileSpreadsheet, Save, Upload } from 'lucide-react';
import { useProject } from '@/context/ProjectContext';
import { ApiError, apiRequest } from '@/lib/api';
import type { ProjectItem, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';

interface TopicPreviewData {
  upload_id: string;
  filename: string;
  topic_pillar_sheet: string;
  topic_pillar_header_row: number | null;
  keywords_sheet: string;
  keywords_header_row: number | null;
  topic_pillars: Array<{
    pillar: string;
    topic_pillar_code: string;
    topic_pillar_name: string;
    topic_type: string;
    split_axis: string;
    main_topic: string;
  }>;
  content_items: Array<{
    topic_pillar_code: string;
    content_code: string;
    content_title: string;
    primary_keyword: string;
    secondary_keywords: string[];
  }>;
  warnings: Array<{ code: string; message: string }>;
  notice: string;
}

export default function Step01TopicPage() {
  const { activeProject, refreshProjects, showCompletionPopup } = useProject();

  const [pillarName, setPillarName] = useState('');
  const [tpCode, setTpCode] = useState('');
  const [tpName, setTpName] = useState('');
  const [topicType, setTopicType] = useState('');
  const [splitAxis, setSplitAxis] = useState('');
  const [mainTopic, setMainTopic] = useState('');
  const [wholePillar, setWholePillar] = useState(false);
  const [contentCode, setContentCode] = useState('');
  const [contentTitle, setContentTitle] = useState('');
  const [primaryKeyword, setPrimaryKeyword] = useState('');
  const [secondaryText, setSecondaryText] = useState('');
  const [businessGoal, setBusinessGoal] = useState('');
  const [targetAudience, setTargetAudience] = useState('');
  const [market, setMarket] = useState('VN');
  const [language, setLanguage] = useState('vi');
  const [softMin, setSoftMin] = useState(5);
  const [softMax, setSoftMax] = useState(7);

  const [preview, setPreview] = useState<TopicPreviewData | null>(null);
  const [selectedTpCode, setSelectedTpCode] = useState('');
  const [selectedContentCode, setSelectedContentCode] = useState('');
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<StandardizedError | null>(null);
  const [infoNotice, setInfoNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!activeProject) return;
    setPillarName(activeProject.pillar_name || '');
    setTpCode(activeProject.topic_pillar_code || activeProject.code || '');
    setTpName(activeProject.topic_pillar_name || '');
    setTopicType(activeProject.topic_type || '');
    setSplitAxis(activeProject.split_axis || '');
    setMainTopic(activeProject.main_topic || '');
    setContentCode(activeProject.content_code || '');
    setContentTitle(activeProject.content_title || '');
    setPrimaryKeyword(activeProject.primary_keyword_current || activeProject.primary_keyword_original || '');
    setSecondaryText((activeProject.secondary_keywords || []).join(', '));
    setBusinessGoal(activeProject.business_goal || '');
    setTargetAudience(activeProject.target_audience || '');
    setMarket(activeProject.market || 'VN');
    setLanguage(activeProject.language || 'vi');
    setSoftMin(activeProject.soft_article_min || 5);
    setSoftMax(activeProject.soft_article_max || 7);
    setPreview(null);
    setInfoNotice(null);
    setError(null);
  }, [activeProject]);

  if (!activeProject) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-surface-900 p-8 text-center text-sm text-slate-300">
        Chưa chọn dự án.{' '}
        <Link href="/projects" className="text-sky-400 underline font-semibold">
          Tạo hoặc chọn dự án trước
        </Link>
        .
      </div>
    );
  }

  const handleFilePreview = async (file: File) => {
    setUploading(true);
    setError(null);
    setInfoNotice(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const data = await apiRequest<TopicPreviewData>(`/api/v1/projects/${activeProject.id}/topic-source/preview`, {
        method: 'POST',
        body: fd,
      });
      setPreview(data);
      const firstTp = data.topic_pillars[0]?.topic_pillar_code || '';
      setSelectedTpCode(firstTp);
      const matchingContent = data.content_items.find((c) => !firstTp || c.topic_pillar_code === firstTp);
      setSelectedContentCode(matchingContent?.content_code || data.content_items[0]?.content_code || '');
      // Notice (T03): Preview NEVER shows completion popup or overwrites form until user clicks "Điền vào form" & confirms!
      setInfoNotice(data.notice);
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setUploading(false);
    }
  };

  const handleApplyToForm = () => {
    if (!preview) return;
    const tp = preview.topic_pillars.find((t) => t.topic_pillar_code === selectedTpCode);
    const ci = preview.content_items.find(
      (c) =>
        c.content_code === selectedContentCode &&
        (!selectedTpCode || !c.topic_pillar_code || c.topic_pillar_code === selectedTpCode)
    );
    if (tp) {
      setPillarName(tp.pillar);
      setTpCode(tp.topic_pillar_code);
      setTpName(tp.topic_pillar_name);
      setTopicType(tp.topic_type);
      setSplitAxis(tp.split_axis);
      setMainTopic(tp.main_topic);
    }
    if (ci) {
      setContentCode(ci.content_code);
      setContentTitle(ci.content_title);
      setPrimaryKeyword(ci.primary_keyword);
      setSecondaryText(ci.secondary_keywords.join(', '));
    }
    // T04: Never guess or carry over business_goal / target_audience from another topic!
    setInfoNotice(
      'Đã điền dữ liệu từ bảng xem trước vào form (chưa ghi SQLite). Vui lòng kiểm tra Mục tiêu kinh doanh & Đối tượng độc giả rồi bấm Lưu.'
    );
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const secList = secondaryText
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    try {
      if (preview) {
        const res = await apiRequest<{
          saved: boolean;
          version: number;
          navigation_eligible: boolean;
          next_step_href: string;
          message: string;
          project: ProjectItem;
        }>(`/api/v1/projects/${activeProject.id}/topic-source/confirm`, {
          method: 'POST',
          body: JSON.stringify({
            upload_id: preview.upload_id,
            selected_topic_pillar_code: tpCode,
            selected_content_code: contentCode,
            source_scope: wholePillar ? "PILLAR" : "CONTENT",
            exclude_keywords_without_volume: true,
            pillar_name: pillarName,
            topic_pillar_name: tpName,
            topic_type: topicType,
            split_axis: splitAxis,
            main_topic: mainTopic,
            content_title: contentTitle,
            primary_keyword: primaryKeyword,
            secondary_keywords: secList,
            business_goal: businessGoal,
            target_audience: targetAudience,
            market,
            language,
            soft_article_min: softMin,
            soft_article_max: softMax,
          }),
        });
        await refreshProjects(activeProject.id);
        setPreview(null);
        showCompletionPopup({
          title: `Đã xác nhận nguồn chủ đề (v${res.version})`,
          message: res.message,
          nextStepLabel: 'Bước 02 — Bản đồ nhu cầu AI',
          nextStepHref: res.next_step_href,
          navigationEligible: res.navigation_eligible,
        });
      } else {
        const res = await apiRequest<{
          saved: boolean;
          version: number;
          primary_change_pending_approval: boolean;
          navigation_eligible: boolean;
          next_step_href: string;
          message: string;
        }>(`/api/v1/projects/${activeProject.id}`, {
          method: 'PUT',
          body: JSON.stringify({
            pillar_name: pillarName,
            topic_pillar_code: tpCode,
            topic_pillar_name: tpName,
            topic_type: topicType,
            split_axis: splitAxis,
            main_topic: mainTopic,
            content_code: contentCode,
            content_title: contentTitle,
            primary_keyword: primaryKeyword,
            secondary_keywords: secList,
            business_goal: businessGoal,
            target_audience: targetAudience,
            market,
            language,
            soft_article_min: softMin,
            soft_article_max: softMax,
          }),
        });
        await refreshProjects(activeProject.id);
        showCompletionPopup({
          title: `Đã lưu Bước 01 (v${res.version})`,
          message: res.message,
          nextStepLabel: res.primary_change_pending_approval ? 'Chờ phê duyệt' : 'Bước 02 — Bản đồ nhu cầu AI',
          nextStepHref: res.primary_change_pending_approval ? '/approvals' : res.next_step_href,
          navigationEligible: res.navigation_eligible,
        });
      }
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    } finally {
      setSaving(false);
    }
  };

  const filteredContents = preview
    ? preview.content_items.filter((c) => !selectedTpCode || !c.topic_pillar_code || c.topic_pillar_code === selectedTpCode)
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Bước 01 — Thiết lập chủ đề & Nguồn từ khóa</h1>
        <p className="mt-1 text-sm text-slate-400">
          Tải file XLSX/CSV chứa bảng Topic Pillar & Keywords (tự nhận diện header không cố định dòng, ví dụ dòng 4) hoặc nhập trực tiếp.
          Bản gốc được giữ nguyên và tạo phiên bản/snapshot trong SQLite.
        </p>
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {/* File Upload Preview Box */}
      <section className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-base font-bold text-slate-100">
            <FileSpreadsheet className="h-5 w-5 text-emerald-400" />
            Nhập nguồn từ Excel / CSV (Xem trước trước khi điền form)
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-emerald-500/15 border border-emerald-500/40 px-4 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25 transition">
            <Upload className="h-4 w-4" />
            {uploading ? 'Đang đọc file…' : 'Chọn file .XLSX / .CSV'}
            <input
              type="file"
              accept=".xlsx,.xlsm,.csv,.tsv"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleFilePreview(f);
                e.target.value = '';
              }}
            />
          </label>
        </div>

        {infoNotice && (
          <div className="rounded-xl border border-sky-500/30 bg-sky-950/25 p-3 text-xs text-sky-200">{infoNotice}</div>
        )}

        <label className="flex gap-2 text-sm"><input type="checkbox" checked={wholePillar} onChange={e=>setWholePillar(e.target.checked)}/>Nghiên cứu toàn bộ mã nội dung trong pillar khi xác nhận file</label>
      <p className="text-xs text-slate-400">Keyword thiếu Volume hoặc Volume 0 sẽ không vào kế hoạch bài viết; dữ liệu nguồn vẫn được giữ để nghiên cứu Semrush.</p>
      {preview && (
          <div className="space-y-4 rounded-xl border border-slate-700/80 bg-surface-850 p-4">
            <div className="flex flex-wrap gap-3 text-xs text-slate-300">
              <span>File: <strong className="text-white">{preview.filename}</strong></span>
              <span>·</span>
              <span>Topic Pillar: <strong>{preview.topic_pillar_sheet || '—'}</strong> (header dòng {preview.topic_pillar_header_row ?? '—'})</span>
              <span>·</span>
              <span>Keywords: <strong>{preview.keywords_sheet || '—'}</strong> (header dòng {preview.keywords_header_row ?? '—'})</span>
            </div>

            {preview.warnings.length > 0 && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-950/25 p-3 space-y-1 text-xs text-amber-200">
                <div className="font-semibold flex items-center gap-1.5">
                  <AlertTriangle className="h-4 w-4 text-amber-400" />
                  Cảnh báo kiểm tra file nguồn ({preview.warnings.length}):
                </div>
                {preview.warnings.slice(0, 6).map((w, i) => (
                  <p key={i}>• [{w.code}] {w.message}</p>
                ))}
              </div>
            )}

            <div className="grid gap-3 md:grid-cols-3 items-end">
              <div>
                <label htmlFor="sel-tp" className="block text-xs font-semibold text-slate-300 mb-1">
                  Chọn Topic Pillar ({preview.topic_pillars.length})
                </label>
                <select
                  id="sel-tp"
                  value={selectedTpCode}
                  onChange={(e) => {
                    const nextCode = e.target.value;
                    setSelectedTpCode(nextCode);
                    const match = preview.content_items.find((c) => c.topic_pillar_code === nextCode);
                    setSelectedContentCode(match?.content_code || '');
                  }}
                  className="finz-select"
                >
                  <option value="">-- Chọn Topic Pillar --</option>
                  {preview.topic_pillars.map((t, i) => (
                    <option key={i} value={t.topic_pillar_code}>
                      [{t.topic_pillar_code}] {t.topic_pillar_name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="sel-cc" className="block text-xs font-semibold text-slate-300 mb-1">
                  Chọn Mã nội dung ({filteredContents.length})
                </label>
                <select
                  id="sel-cc"
                  value={selectedContentCode}
                  onChange={(e) => setSelectedContentCode(e.target.value)}
                  className="finz-select"
                >
                  <option value="">-- Chọn Mã nội dung --</option>
                  {filteredContents.map((c, i) => (
                    <option key={i} value={c.content_code}>
                      [{c.content_code}] {c.content_title || c.primary_keyword}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="button"
                onClick={handleApplyToForm}
                className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 transition"
              >
                <ArrowDownToLine className="h-4 w-4" />
                Điền vào form
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Topic Setup Form */}
      <form onSubmit={handleSave} className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <h2 className="text-base font-bold text-slate-100">Thông tin Topic Pillar & Keyword gốc</h2>
          <span className="text-xs text-slate-400">
            Keyword chính gốc đang lưu: <strong className="text-sky-300">{activeProject.primary_keyword_original || '(chưa có)'}</strong>
          </span>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label htmlFor="f-pillar" className="block text-xs font-semibold text-slate-300 mb-1">Pillar</label>
            <input id="f-pillar" value={pillarName} onChange={(e) => setPillarName(e.target.value)} className="finz-input" />
          </div>
          <div>
            <label htmlFor="f-tpcode" className="block text-xs font-semibold text-slate-300 mb-1">Mã Topic Pillar *</label>
            <input id="f-tpcode" required data-error="f-tpcode-err" value={tpCode} onChange={(e) => setTpCode(e.target.value)} className="finz-input font-mono" />
            <div id="f-tpcode-err" className="field-error-msg">Cần mã Topic Pillar.</div>
          </div>
          <div>
            <label htmlFor="f-tpname" className="block text-xs font-semibold text-slate-300 mb-1">Tên Topic Pillar *</label>
            <input id="f-tpname" required data-error="f-tpname-err" value={tpName} onChange={(e) => setTpName(e.target.value)} className="finz-input" />
            <div id="f-tpname-err" className="field-error-msg">Cần tên Topic Pillar.</div>
          </div>

          <div>
            <label htmlFor="f-tptype" className="block text-xs font-semibold text-slate-300 mb-1">Loại topic</label>
            <input id="f-tptype" value={topicType} onChange={(e) => setTopicType(e.target.value)} placeholder="Core Pillar / Cluster…" className="finz-input" />
          </div>
          <div>
            <label htmlFor="f-axis" className="block text-xs font-semibold text-slate-300 mb-1">Trục chia</label>
            <input id="f-axis" value={splitAxis} onChange={(e) => setSplitAxis(e.target.value)} className="finz-input" />
          </div>
          <div>
            <label htmlFor="f-main" className="block text-xs font-semibold text-slate-300 mb-1">Chủ đề chính</label>
            <input id="f-main" value={mainTopic} onChange={(e) => setMainTopic(e.target.value)} className="finz-input" />
          </div>

          <div>
            <label htmlFor="f-ccode" className="block text-xs font-semibold text-slate-300 mb-1">Mã nội dung</label>
            <input id="f-ccode" value={contentCode} onChange={(e) => setContentCode(e.target.value)} placeholder="VD: P08-01" className="finz-input font-mono" />
          </div>
          <div className="md:col-span-2">
            <label htmlFor="f-ctitle" className="block text-xs font-semibold text-slate-300 mb-1">Tiêu đề dự kiến</label>
            <input id="f-ctitle" value={contentTitle} onChange={(e) => setContentTitle(e.target.value)} className="finz-input" />
          </div>

          <div className="md:col-span-1">
            <label htmlFor="f-pk" className="block text-xs font-semibold text-slate-300 mb-1">Keyword chính *</label>
            <span className="block text-[11px] text-slate-500 mb-1">Đổi keyword chính gốc sẽ tạo yêu cầu Chờ phê duyệt.</span>
            <input id="f-pk" required data-error="f-pk-err" value={primaryKeyword} onChange={(e) => setPrimaryKeyword(e.target.value)} className="finz-input" />
            <div id="f-pk-err" className="field-error-msg">Cần nhập Keyword chính.</div>
          </div>
          <div className="md:col-span-2">
            <label htmlFor="f-sk" className="block text-xs font-semibold text-slate-300 mb-1">Keyword phụ (cách nhau bằng dấu phẩy hoặc xuống dòng)</label>
            <textarea id="f-sk" rows={2} value={secondaryText} onChange={(e) => setSecondaryText(e.target.value)} className="finz-textarea" />
          </div>

          <div className="md:col-span-2">
            <label htmlFor="f-goal" className="block text-xs font-semibold text-slate-300 mb-1">Mục tiêu kinh doanh</label>
            <input id="f-goal" value={businessGoal} onChange={(e) => setBusinessGoal(e.target.value)} placeholder="Chủ động nhập — hệ thống không tự đoán từ file" className="finz-input" />
          </div>
          <div>
            <label htmlFor="f-aud" className="block text-xs font-semibold text-slate-300 mb-1">Đối tượng độc giả</label>
            <input id="f-aud" value={targetAudience} onChange={(e) => setTargetAudience(e.target.value)} placeholder="VD: Kế toán trưởng SME" className="finz-input" />
          </div>

          <div>
            <label htmlFor="f-mkt" className="block text-xs font-semibold text-slate-300 mb-1">Thị trường</label>
            <input id="f-mkt" value={market} onChange={(e) => setMarket(e.target.value)} className="finz-input" />
          </div>
          <div>
            <label htmlFor="f-lang" className="block text-xs font-semibold text-slate-300 mb-1">Ngôn ngữ</label>
            <input id="f-lang" value={language} onChange={(e) => setLanguage(e.target.value)} className="finz-input" />
          </div>
          <div>
            <span className="block text-xs font-semibold text-slate-300 mb-1">Mục tiêu bài ARTICLE mềm (không ép đủ)</span>
            <div className="flex items-center gap-2">
              <input type="number" min={1} max={30} value={softMin} onChange={(e) => setSoftMin(Number(e.target.value) || 5)} className="finz-input text-center" aria-label="Tối thiểu bài viết" />
              <span className="text-slate-400">–</span>
              <input type="number" min={1} max={50} value={softMax} onChange={(e) => setSoftMax(Number(e.target.value) || 7)} className="finz-input text-center" aria-label="Tối đa bài viết" />
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800">
          <p className="text-xs text-slate-400">
            Chỉ hiển thị xác nhận hoàn thành sau khi backend commit vào SQLite thành công.
          </p>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-2 rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
          >
            <Save className="h-4 w-4" />
            {saving ? 'Đang lưu SQLite…' : preview ? 'Xác nhận nhập file & Lưu SQLite' : 'Lưu cấu hình vào SQLite'}
          </button>
        </div>
      </form>
    </div>
  );
}

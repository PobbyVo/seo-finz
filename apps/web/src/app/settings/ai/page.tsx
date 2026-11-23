'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2,
  Cpu,
  HelpCircle,
  KeyRound,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
  Zap,
} from 'lucide-react';
import { KnowledgeSettings } from '@/components/KnowledgeSettings';
import { ApiError, apiRequest } from '@/lib/api';
import { useProject } from '@/context/ProjectContext';
import type { AIProviderInfo, StandardizedError } from '@/lib/types';
import { ErrorBanner } from '@/components/ErrorBanner';
import { StatusBadge } from '@/components/StatusBadge';

const PROVIDER_TABS: Array<{
  id: 'gemini' | 'openai' | 'claude' | 'mock';
  label: string;
  tagline: string;
  keyHint: string;
  defaultModelPlaceholder: string;
}> = [
  {
    id: 'gemini',
    label: 'Google Gemini',
    tagline: 'Tự lấy model mới nhất · Lỗi 3 lần tự động hạ model',
    keyHint: 'Lấy API key tại Google AI Studio (aistudio.google.com).',
    defaultModelPlaceholder: 'auto (tự chọn model Gemini mới nhất)',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    tagline: 'OpenAI Platform API (không phải đăng nhập ChatGPT/Codex)',
    keyHint: 'Lấy API key tại platform.openai.com/api-keys.',
    defaultModelPlaceholder: 'gpt-4.1-mini hoặc gpt-4.1',
  },
  {
    id: 'claude',
    label: 'Anthropic Claude',
    tagline: 'Anthropic Messages API chính thức',
    keyHint: 'Lấy API key tại console.anthropic.com.',
    defaultModelPlaceholder: 'claude-sonnet-4-5',
  },
  {
    id: 'mock',
    label: 'Mock Provider (0đ)',
    tagline: 'Chạy thử nghiệm local không phát sinh chi phí API',
    keyHint: 'Không cần API key — dùng cho kiểm thử luồng SEO offline.',
    defaultModelPlaceholder: 'finz-mock-deterministic-v1',
  },
];

export default function AISettingsPage() {
  const { refreshAISettings } = useProject();
  const [providers, setProviders] = useState<AIProviderInfo[]>([]);
  const [selected, setSelected] = useState<'gemini' | 'openai' | 'claude' | 'mock'>('gemini');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [modelId, setModelId] = useState('auto');
  const [endpointUrl, setEndpointUrl] = useState('');
  const [useSharedModel, setUseSharedModel] = useState(true);
  const [analystModelId, setAnalystModelId] = useState('');
  const [criticModelId, setCriticModelId] = useState('');
  const [autoLatest, setAutoLatest] = useState(true);
  const [downgradeThreshold, setDowngradeThreshold] = useState(3);
  const [setActive, setSetActive] = useState(true);

  const [securityNotice, setSecurityNotice] = useState('');
  const [costNotice, setCostNotice] = useState('');
  const [showGuide, setShowGuide] = useState(false);

  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [syncingModels, setSyncingModels] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [fallbackNotices, setFallbackNotices] = useState<Array<{ from_model: string; to_model: string; reason: string }>>([]);
  const [error, setError] = useState<StandardizedError | null>(null);

  const loadSettings = useCallback(async (preferTab?: 'gemini' | 'openai' | 'claude' | 'mock') => {
    try {
      const data = await apiRequest<{
        active_provider: string | null;
        providers: AIProviderInfo[];
        security_notice: string;
        cost_notice: string;
      }>('/api/v1/settings/ai');
      setProviders(data.providers);
      setSecurityNotice(data.security_notice);
      setCostNotice(data.cost_notice);

      const targetId = preferTab || (data.active_provider as 'gemini' | 'openai' | 'claude' | 'mock') || 'gemini';
      setSelected(targetId);
      const item = data.providers.find((p) => p.provider === targetId);
      if (item) {
        setModelId(item.model_id);
        setEndpointUrl(item.endpoint_url);
        setUseSharedModel(item.use_shared_model);
        setAnalystModelId(item.analyst_model_id || '');
        setCriticModelId(item.critic_model_id || '');
        setAutoLatest(item.auto_latest);
        setDowngradeThreshold(item.downgrade_threshold || 3);
      }
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  }, []);

  useEffect(() => {
    // Notice (T09): Opening Settings ONLY loads metadata — NEVER auto-triggers billed Test Connection!
    void loadSettings();
  }, [loadSettings]);

  const currentProvider = providers.find((p) => p.provider === selected) || null;
  const tabMeta = PROVIDER_TABS.find((t) => t.id === selected)!;

  const handleSelectTab = (id: 'gemini' | 'openai' | 'claude' | 'mock') => {
    setSelected(id);
    setApiKeyInput('');
    setStatusMessage(null);
    setError(null);
    setFallbackNotices([]);
    const item = providers.find((p) => p.provider === id);
    if (item) {
      setModelId(item.model_id);
      setEndpointUrl(item.endpoint_url);
      setUseSharedModel(item.use_shared_model);
      setAnalystModelId(item.analyst_model_id || '');
      setCriticModelId(item.critic_model_id || '');
      setAutoLatest(item.auto_latest);
      setDowngradeThreshold(item.downgrade_threshold || 3);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setStatusMessage(null);
    try {
      const res = await apiRequest<{ saved: boolean; provider: AIProviderInfo }>('/api/v1/settings/ai', {
        method: 'PUT',
        body: JSON.stringify({
          provider: selected,
          set_active: setActive,
          api_key: apiKeyInput.trim() || null,
          model_id: selected === 'gemini' && autoLatest ? 'auto' : modelId.trim(),
          use_shared_model: useSharedModel,
          analyst_model_id: useSharedModel ? null : analystModelId.trim() || null,
          critic_model_id: useSharedModel ? null : criticModelId.trim() || null,
          endpoint_url: endpointUrl.trim() || null,
          auto_latest: selected === 'gemini' ? autoLatest : false,
          downgrade_threshold: selected === 'gemini' ? downgradeThreshold : 3,
        }),
      });
      setApiKeyInput('');
      setStatusMessage(
        `Đã lưu cấu hình ${selected.toUpperCase()} thành công (model hiện hành: ${res.provider.active_model_id || res.provider.model_id}). Bấm "Kiểm tra kết nối" để xác minh thực tế.`
      );
      await loadSettings(selected);
      await refreshAISettings();
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
      else setError({ code: 'DB_SAVE_FAILED', reason: String(err), impact: 'Chưa lưu được cấu hình AI.', solution: 'Kiểm tra lại thông tin.', next_action: 'Thử lưu lại.' });
    } finally {
      setSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setError(null);
    setStatusMessage(null);
    setFallbackNotices([]);
    try {
      const res = await apiRequest<{
        ok: boolean;
        actual_model: string;
        latency_ms: number;
        status: string;
        message: string;
        fallback_events: Array<{ from_model: string; to_model: string; reason: string }>;
        error: StandardizedError | null;
      }>('/api/v1/settings/ai/test', {
        method: 'POST',
        body: JSON.stringify({
          provider: selected,
          api_key: apiKeyInput.trim() || null,
          model_id: selected === 'gemini' && autoLatest ? 'auto' : modelId.trim(),
          endpoint_url: endpointUrl.trim() || null,
          auto_latest: selected === 'gemini' ? autoLatest : undefined,
          downgrade_threshold: selected === 'gemini' ? downgradeThreshold : undefined,
        }),
      });
      if (res.fallback_events?.length) {
        setFallbackNotices(res.fallback_events);
      }
      if (res.ok) {
        setStatusMessage(`${res.message} (Model thực tế: ${res.actual_model} · ${res.latency_ms} ms)`);
      } else if (res.error) {
        setError(res.error);
      }
      await loadSettings(selected);
      await refreshAISettings();
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
      else
        setError({
          code: 'CONNECTION_TIMEOUT',
          reason: err instanceof Error ? err.message : String(err),
          impact: 'Không nhận được kết quả kiểm tra kết nối từ backend.',
          solution: 'Kiểm tra log terminal `npm run dev` và thử bấm Kiểm tra kết nối lại.',
          next_action: 'Thử lại sau khi kiểm tra kết nối.',
        });
    } finally {
      setTesting(false);
    }
  };

  const handleSyncGeminiModels = async () => {
    setSyncingModels(true);
    setError(null);
    setStatusMessage(null);
    try {
      const res = await apiRequest<{
        discovered_count: number;
        active_model_id: string;
      }>('/api/v1/settings/ai/gemini/sync-models', { method: 'POST' });
      setStatusMessage(
        `Đã đồng bộ ${res.discovered_count} model từ Google Gemini API. Model mới nhất ưu tiên hiện tại: ${res.active_model_id}.`
      );
      await loadSettings('gemini');
      await refreshAISettings();
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
      else
        setError({
          code: 'CONNECTION_TIMEOUT',
          reason: err instanceof Error ? err.message : String(err),
          impact: 'Không nhận được kết quả kiểm tra kết nối từ backend.',
          solution: 'Kiểm tra log terminal `npm run dev` và thử bấm Kiểm tra kết nối lại.',
          next_action: 'Thử lại sau khi kiểm tra kết nối.',
        });
    } finally {
      setSyncingModels(false);
    }
  };

  const handleResetGeminiLatest = async () => {
    setError(null);
    try {
      const res = await apiRequest<{ message: string }>('/api/v1/settings/ai/gemini/reset-latest', { method: 'POST' });
      setStatusMessage(res.message);
      await loadSettings('gemini');
      await refreshAISettings();
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  };

  const handleDeleteKey = async () => {
    if (!window.confirm(`Xóa API key đã lưu của ${selected.toUpperCase()}?`)) return;
    setError(null);
    try {
      await apiRequest(`/api/v1/settings/ai/${selected}`, { method: 'DELETE' });
      setStatusMessage(`Đã thu hồi & xóa API key của ${selected.toUpperCase()}.`);
      await loadSettings(selected);
      await refreshAISettings();
    } catch (err) {
      if (err instanceof ApiError && err.structured) setError(err.structured);
    }
  };

  return (
    <div className="space-y-6">
      <KnowledgeSettings />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Settings → AI Providers</h1>
          <p className="mt-1 text-sm text-slate-400">
            Cấu hình nhà cung cấp AI (Google Gemini, OpenAI, Anthropic Claude hoặc Mock 0đ) trực tiếp trên giao diện, không cần sửa file <code className="text-slate-200">.env.local</code>.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowGuide((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-surface-900 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
        >
          <HelpCircle className="h-4 w-4 text-sky-400" />
          {showGuide ? 'Ẩn hướng dẫn' : 'Xem hướng dẫn'}
        </button>
      </div>

      {showGuide && (
        <div className="rounded-2xl border border-sky-500/30 bg-sky-950/20 p-4 text-xs text-slate-300 space-y-2">
          <p><strong className="text-sky-200">1. Cơ chế Gemini tự động mới nhất & hạ bậc sau 3 lỗi:</strong> Khi chọn Google Gemini ở chế độ <em>Auto-latest</em>, hệ thống luôn chọn model Gemini mới nhất. Nếu model hiện hành gặp lỗi <strong>3 lần liên tiếp</strong> (quota, quá tải, 404, timeout…), backend tự động hạ xuống model kế tiếp trong chuỗi dự phòng và ghi nhật ký rõ ràng.</p>
          <p><strong className="text-sky-200">2. Bảo mật API Key:</strong> {securityNotice}</p>
          <p><strong className="text-sky-200">3. Lưu ý chi phí:</strong> {costNotice}</p>
          <p><strong className="text-sky-200">4. OpenAI vs ChatGPT/Codex:</strong> Không có &quot;Codex API key&quot; riêng — hãy sử dụng OpenAI Platform API key.</p>
        </div>
      )}

      {/* Provider Selector Grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {PROVIDER_TABS.map((tab) => {
          const info = providers.find((p) => p.provider === tab.id);
          const active = selected === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => handleSelectTab(tab.id)}
              className={`rounded-2xl border p-4 text-left transition ${
                active
                  ? 'border-violet-400/60 bg-violet-950/30 shadow-lg shadow-violet-950/30'
                  : 'border-slate-800 bg-surface-900 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-bold text-slate-100">{tab.label}</span>
                {info?.is_active && (
                  <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/40">
                    ĐANG DÙNG
                  </span>
                )}
              </div>
              <p className="mt-1 text-[11px] text-slate-400 leading-snug">{tab.tagline}</p>
              <div className="mt-3 flex items-center justify-between gap-2">
                <StatusBadge status={info?.connection_status || 'NOT_CONFIGURED'} />
                {info?.last_latency_ms != null && (
                  <span className="font-mono text-[11px] text-slate-500">{info.last_latency_ms}ms</span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {statusMessage && (
        <div className="rounded-xl border border-emerald-500/35 bg-emerald-950/30 p-4 text-sm text-emerald-200 flex items-start gap-2.5">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400 mt-0.5" />
          <div>{statusMessage}</div>
        </div>
      )}

      {fallbackNotices.length > 0 && (
        <div className="rounded-xl border border-amber-500/35 bg-amber-950/30 p-4 text-xs text-amber-200 space-y-1">
          <div className="font-bold flex items-center gap-1.5">
            <Zap className="h-4 w-4 text-amber-400" />
            Gemini đã tự động hạ model sau 3 lần lỗi:
          </div>
          {fallbackNotices.map((ev, idx) => (
            <p key={idx}>• {ev.reason}</p>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Configuration Form */}
        <form onSubmit={handleSave} className="lg:col-span-2 rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-violet-400" />
              <h2 className="text-base font-bold text-slate-100">Cấu hình {tabMeta.label}</h2>
            </div>
            {currentProvider && <StatusBadge status={currentProvider.connection_status} />}
          </div>

          {selected !== 'mock' && (
            <div>
              <label htmlFor="ai-api-key" className="block text-xs font-semibold text-slate-300 mb-1">
                API Key ({tabMeta.label})
              </label>
              <span className="block text-[11px] text-slate-500 mb-1.5">
                {tabMeta.keyHint}{' '}
                {currentProvider?.key_hint && (
                  <strong className="text-emerald-300">
                    Đang lưu: {currentProvider.key_hint} ({currentProvider.secret_storage_mode})
                  </strong>
                )}
              </span>
              <input
                id="ai-api-key"
                type="password"
                autoComplete="off"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                placeholder={currentProvider?.has_key ? 'Để trống nếu giữ nguyên API key đã lưu trong Keychain' : 'Dán API key vào đây…'}
                className="finz-input font-mono"
              />
            </div>
          )}

          {/* Gemini Auto-Latest & 3-Failure Auto-Downgrade Controls */}
          {selected === 'gemini' && (
            <div className="rounded-xl border border-sky-500/30 bg-sky-950/20 p-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2.5 cursor-pointer text-sm font-semibold text-sky-200">
                  <input
                    type="checkbox"
                    checked={autoLatest}
                    onChange={(e) => {
                      setAutoLatest(e.target.checked);
                      if (e.target.checked) setModelId('auto');
                    }}
                    className="h-4 w-4 rounded"
                  />
                  Tự động lấy model Gemini mới nhất (Auto-Latest)
                </label>
                <div className="flex items-center gap-2">
                  <label htmlFor="downgrade-threshold" className="text-xs text-slate-300">
                    Tự hạ model sau
                  </label>
                  <input
                    id="downgrade-threshold"
                    type="number"
                    min={1}
                    max={10}
                    value={downgradeThreshold}
                    onChange={(e) => setDowngradeThreshold(Math.max(1, Number(e.target.value) || 3))}
                    className="finz-input w-16 py-1 text-center font-mono"
                  />
                  <span className="text-xs text-slate-300">lần lỗi</span>
                </div>
              </div>
              <p className="text-xs text-slate-400">
                Khi bật, hệ thống ưu tiên model Gemini mới nhất trong chuỗi khả dụng. Nếu model đó lỗi liên tiếp{' '}
                <strong className="text-sky-300">{downgradeThreshold} lần</strong>, backend tự động hạ xuống model kế tiếp
                và tiếp tục công việc mà không gián đoạn.
              </p>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="ai-model-id" className="block text-xs font-semibold text-slate-300 mb-1">
                Model ID {selected === 'gemini' && autoLatest ? '(đang ở chế độ Auto-Latest)' : ''}
              </label>
              <input
                id="ai-model-id"
                value={selected === 'gemini' && autoLatest ? 'auto' : modelId}
                disabled={selected === 'gemini' && autoLatest}
                onChange={(e) => setModelId(e.target.value)}
                placeholder={tabMeta.defaultModelPlaceholder}
                className="finz-input font-mono disabled:opacity-60"
              />
            </div>

            <div>
              <label htmlFor="ai-endpoint" className="block text-xs font-semibold text-slate-300 mb-1">
                Endpoint chính thức (được kiểm soát chống SSRF)
              </label>
              <input
                id="ai-endpoint"
                value={endpointUrl}
                onChange={(e) => setEndpointUrl(e.target.value)}
                className="finz-input font-mono text-xs"
              />
            </div>
          </div>

          {/* Shared vs Split Analyst/Critic Models */}
          <div className="space-y-3 rounded-xl border border-slate-800 bg-surface-850/70 p-3.5">
            <label className="flex items-center gap-2 text-xs font-semibold text-slate-200 cursor-pointer">
              <input
                type="checkbox"
                checked={useSharedModel}
                onChange={(e) => setUseSharedModel(e.target.checked)}
                className="h-4 w-4 rounded"
              />
              Dùng chung một model cho cả AI Topic Analyst & AI SEO Critic (mặc định)
            </label>
            {!useSharedModel && (
              <div className="grid gap-3 sm:grid-cols-2 pt-1">
                <div>
                  <label htmlFor="analyst-model" className="block text-xs text-slate-400 mb-1">Model riêng cho Analyst</label>
                  <input
                    id="analyst-model"
                    value={analystModelId}
                    onChange={(e) => setAnalystModelId(e.target.value)}
                    placeholder="Ví dụ: gemini-3.8-flash"
                    className="finz-input font-mono text-xs"
                  />
                </div>
                <div>
                  <label htmlFor="critic-model" className="block text-xs text-slate-400 mb-1">Model riêng cho Critic</label>
                  <input
                    id="critic-model"
                    value={criticModelId}
                    onChange={(e) => setCriticModelId(e.target.value)}
                    placeholder="Ví dụ: gemini-4-argon"
                    className="finz-input font-mono text-xs"
                  />
                </div>
              </div>
            )}
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={setActive}
              onChange={(e) => setSetActive(e.target.checked)}
              className="h-4 w-4 rounded"
            />
            Đặt <strong>{tabMeta.label}</strong> làm nhà cung cấp AI đang hoạt động (không tự đổi sang provider khác có phí nếu bạn chưa chọn)
          </label>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-slate-800">
            <button
              type="submit"
              disabled={saving}
              className="rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 transition"
            >
              {saving ? 'Đang lưu…' : 'Lưu cấu hình'}
            </button>
            <button
              type="button"
              onClick={() => void handleTestConnection()}
              disabled={testing}
              className="inline-flex items-center gap-1.5 rounded-xl bg-violet-500/20 border border-violet-400/40 px-4 py-2.5 text-sm font-semibold text-violet-200 hover:bg-violet-500/30 disabled:opacity-50 transition"
            >
              <Zap className="h-4 w-4" />
              {testing ? 'Đang kiểm tra…' : 'Kiểm tra kết nối'}
            </button>
            {selected !== 'mock' && currentProvider?.has_key && (
              <button
                type="button"
                onClick={() => void handleDeleteKey()}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/35 bg-rose-950/30 px-3.5 py-2.5 text-xs font-semibold text-rose-300 hover:bg-rose-950/60 ml-auto transition"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Xóa key
              </button>
            )}
          </div>

          <p className="text-[11px] text-slate-500 flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400 shrink-0" />
            {costNotice || 'Bấm Kiểm tra kết nối có thể phát sinh một request nhỏ tới nhà cung cấp AI (trừ Mock Provider).'}
          </p>
        </form>

        {/* Side Status & Gemini Fallback Ladder */}
        <aside className="rounded-2xl border border-slate-800 bg-surface-900 p-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-100">
            <Cpu className="h-4 w-4 text-sky-400" />
            Trạng thái thực tế ({tabMeta.label})
          </div>

          <dl className="space-y-2 text-xs">
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Model đang dùng:</dt>
              <dd className="font-mono font-semibold text-sky-300 text-right">
                {currentProvider?.active_model_id || currentProvider?.model_id || '—'}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Lưu trữ key:</dt>
              <dd className="font-mono text-slate-200">{currentProvider?.secret_storage_mode || 'none'}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Kiểm tra gần nhất:</dt>
              <dd className="text-slate-200">
                {currentProvider?.last_tested_at
                  ? new Date(currentProvider.last_tested_at).toLocaleString('vi-VN')
                  : 'Chưa kiểm tra'}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-400">Độ trễ gần nhất:</dt>
              <dd className="font-mono text-slate-200">
                {currentProvider?.last_latency_ms != null ? `${currentProvider.last_latency_ms} ms` : '—'}
              </dd>
            </div>
          </dl>

          {selected === 'gemini' && currentProvider && (
            <div className="pt-3 border-t border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-sky-300 flex items-center gap-1.5">
                  <Sparkles className="h-3.5 w-3.5" />
                  Chuỗi tự động hạ model (ngưỡng {currentProvider.downgrade_threshold} lỗi)
                </h3>
              </div>
              {currentProvider.last_downgrade_reason && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-950/25 p-2.5 text-[11px] text-amber-200">
                  <strong>Hạ bậc gần nhất:</strong> {currentProvider.last_downgrade_reason}
                </div>
              )}
              <ol className="space-y-1.5 text-xs">
                {(currentProvider.fallback_chain || []).map((m, idx) => {
                  const isActiveModel = currentProvider.active_model_id === m;
                  const fails = currentProvider.failure_counts?.[m] || 0;
                  return (
                    <li
                      key={m}
                      className={`flex items-center justify-between rounded-lg px-2.5 py-1.5 font-mono text-[11px] ${
                        isActiveModel
                          ? 'bg-sky-500/15 text-sky-200 border border-sky-500/40 font-semibold'
                          : 'bg-surface-850 text-slate-400 border border-slate-800'
                      }`}
                    >
                      <span className="truncate">
                        {idx + 1}. {m}
                      </span>
                      <span className={fails > 0 ? 'text-amber-300' : 'text-slate-500'}>
                        {fails}/{currentProvider.downgrade_threshold} lỗi
                      </span>
                    </li>
                  );
                })}
              </ol>

              <div className="flex flex-col gap-2 pt-1">
                <button
                  type="button"
                  disabled={syncingModels || !currentProvider.has_key}
                  onClick={() => void handleSyncGeminiModels()}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-sky-500/35 bg-sky-500/10 px-3 py-2 text-xs font-semibold text-sky-200 hover:bg-sky-500/20 disabled:opacity-40"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${syncingModels ? 'animate-spin' : ''}`} />
                  Đồng bộ model mới nhất từ Google
                </button>
                <button
                  type="button"
                  onClick={() => void handleResetGeminiLatest()}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-700 bg-surface-850 px-3 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Khôi phục model mới nhất & reset lỗi
                </button>
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

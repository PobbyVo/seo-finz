import httpx
from app.ai.adapters.base import ProviderConfig
from app.ai.adapters.gemini_adapter import GeminiAdapter, build_effective_chain


def test_timeout_budget_allows_three_failures_then_next_model(monkeypatch):
    elapsed=[0.0];calls=[]
    monkeypatch.setattr('app.ai.adapters.gemini_adapter.time.perf_counter',lambda:elapsed[0])
    def handler(request):
        model=request.url.path.split('/models/')[1].split(':')[0]
        calls.append(model)
        if model=='gemini-new-preview':
            elapsed[0]+=40
            raise httpx.ReadTimeout('timeout',request=request)
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}]})
    adapter=GeminiAdapter(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result=adapter.generate_structured_output(ProviderConfig(provider='gemini',api_key='test-only',model_id='gemini-new-preview',endpoint_url='https://generativelanguage.googleapis.com/v1beta',timeout_seconds=45,fallback_chain=['gemini-new-preview','gemini-next-flash']), 'JSON', 'test')
    assert result.ok
    assert calls==['gemini-new-preview']*3+['gemini-next-flash']
    assert result.fallback_events[0].failures_on_model==3


def test_stable_fallbacks_survive_long_preview_cache():
    chain=build_effective_chain('auto',existing_chain=[f'gemini-9-preview-{i}' for i in range(20)])
    assert 'gemini-2.5-flash' in chain
    assert 'gemini-2.5-flash-lite' in chain


def test_cached_three_failures_skip_model_without_fourth_request():
    calls=[]
    def handler(request):
        calls.append(request.url.path.split('/models/')[1].split(':')[0])
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}]})
    adapter=GeminiAdapter(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    config=ProviderConfig(provider='gemini',api_key='test-only',model_id='gemini-new-preview',endpoint_url='https://generativelanguage.googleapis.com/v1beta',fallback_chain=['gemini-new-preview','gemini-next-flash'],failure_counts={'gemini-new-preview':3})
    result=adapter.generate_structured_output(config,'JSON','test')
    assert result.ok
    assert calls==['gemini-next-flash']

'use client';
import { useEffect, useState } from 'react';
import { apiRequest } from '@/lib/api';

const labels: Record<string, string> = {
 status: 'Trạng thái', p1_min_volume: 'P1: Volume tối thiểu', p1_max_kd: 'P1: KD tối đa', p2_min_volume: 'P2: Volume tối thiểu',
 backlog_min_top10: 'Backlog: số trang cùng loại /10', article_min_top10: 'Bài viết: số bài cùng intent /10', explanation_min_top10: 'Bài giải thích: số bài /10',
 mandatory_idea_min_pages: 'Ý bắt buộc: số bài lặp lại', merge_min_shared_urls: 'Gộp key: số URL chung', max_supplement_rounds: 'Số vòng bổ sung tối đa', stale_days: 'Số ngày dữ liệu được coi là cũ',
 read_pages_min: 'Số trang đọc tối thiểu', read_pages_max: 'Số trang đọc tối đa', brief_repair_attempts: 'Số lần sửa brief', allow_pending_drafts: 'Cho phép yêu cầu brief nháp chưa duyệt', allow_p0: 'Giữ mức ưu tiên P0', fetch_serp_pages: 'Cho phép đọc trang SERP qua kiểm tra SSRF',
};
export function KnowledgeSettings() {
 const [values,setValues]=useState<Record<string,string|number|boolean>>({});
 const [message,setMessage]=useState('');
 useEffect(()=>{apiRequest<{thresholds:Record<string,string|number|boolean>}>('/api/v1/settings/knowledge').then(r=>setValues(r.thresholds)).catch(e=>setMessage(e.message));},[]);
 return <details className="card p-5"><summary className="cursor-pointer font-semibold">Playbook & ngưỡng nghiệp vụ — đề xuất, chờ sếp chốt</summary><div className="grid gap-3 mt-4 sm:grid-cols-2">{Object.entries(values).map(([key,value])=><label key={key} className="flex flex-col gap-1 text-sm">{labels[key]||key}<input className="input" type={typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'text'} checked={typeof value==='boolean'?value:undefined} value={typeof value==='boolean'?undefined:value} onChange={e=>setValues({...values,[key]:typeof value==='boolean'?e.target.checked:typeof value==='number'?Number(e.target.value):e.target.value})}/></label>)}</div><button className="btn-primary mt-4" onClick={async()=>{try{await apiRequest('/api/v1/settings/knowledge',{method:'PUT',body:JSON.stringify(values)});setMessage('Đã lưu ngưỡng đề xuất.');}catch(e){setMessage(e instanceof Error?e.message:'Không lưu được cấu hình.');}}}>Lưu ngưỡng đề xuất</button><p role="status">{message}</p></details>;
}

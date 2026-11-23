import json
import os
import tempfile
from fastapi import APIRouter, HTTPException
from app.knowledge import ROOT, load_thresholds, playbook

router = APIRouter(prefix="/settings/knowledge", tags=["settings"])


@router.get("")
def get_knowledge():
    return {"thresholds": load_thresholds(), "playbook": playbook()}


@router.put("")
def save_knowledge(payload: dict):
    current = load_thresholds()
    if set(payload) != set(current):
        raise HTTPException(422, "Cần gửi đủ các trường cấu hình đã hiển thị.")
    for key, old in current.items():
        value = payload[key]
        if type(value) is not type(old) or (
            type(old) is int and (value < 0 or value > 1000000)
        ):
            raise HTTPException(422, f"Giá trị cấu hình không hợp lệ: {key}")
    if (
        payload["read_pages_min"] > payload["read_pages_max"]
        or payload["read_pages_max"] > 5
        or payload["p1_max_kd"] > 100
    ):
        raise HTTPException(422, "Khoảng số trang hoặc KD không hợp lệ.")
    if payload["brief_repair_attempts"] > 5 or payload["max_supplement_rounds"] > 5:
        raise HTTPException(422, "Số lượt sửa/bổ sung tối đa trong cấu hình là 5.")
    descriptor, path = tempfile.mkstemp(dir=ROOT, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(path, ROOT / "thresholds.yaml")
    finally:
        if os.path.exists(path):
            os.unlink(path)
    return {
        "thresholds": payload,
        "message": "Đã lưu ngưỡng đề xuất. Các quyết định cần người duyệt.",
    }

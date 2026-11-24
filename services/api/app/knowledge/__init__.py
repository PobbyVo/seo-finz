"""Playbook và ngưỡng đề xuất đọc ở runtime; JSON là tập con hợp lệ của YAML."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent


def load_thresholds():
    return json.loads((ROOT / "thresholds.yaml").read_text())


def playbook():
    return (ROOT / "finz_playbook.md").read_text()


def prompt_hash(prompt):
    return hashlib.sha256(
        (
            prompt
            + playbook()
            + json.dumps(load_thresholds(), sort_keys=True, ensure_ascii=False)
        ).encode()
    ).hexdigest()[:40]


def priority_for(volume, kd, *, funnel_stage="", course_relevant=False):
    t = load_thresholds()
    if (
        volume is not None
        and kd is not None
        and volume >= t["p1_min_volume"]
        and kd <= t["p1_max_kd"]
    ):
        return (
            "P1",
            f"Volume {volume} ≥ {t['p1_min_volume']}; KD {kd} ≤ {t['p1_max_kd']} (ngưỡng đề xuất).",
        )
    if (volume is not None and volume >= t["p2_min_volume"]) or (
        funnel_stage == "BOFU" and course_relevant
    ):
        return (
            "P2",
            f"Volume {volume if volume is not None else 'chưa có'}; BOFU sát khóa học: {course_relevant} (ngưỡng đề xuất).",
        )
    return (
        "P3",
        f"Volume {volume if volume is not None else 'chưa có'}; KD {kd if kd is not None else 'chưa có'}: chưa đạt ngưỡng P1/P2 đề xuất.",
    )

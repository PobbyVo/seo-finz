from app.knowledge import priority_for, prompt_hash, load_thresholds


def test_priority_uses_both_metrics():
    assert priority_for(9900, 21)[0] == "P1"
    assert priority_for(9900, 70)[0] == "P2"
    assert priority_for(None, None)[0] == "P3"
    assert priority_for(0, 0)[0] == "P3"
    assert (
        priority_for(None, None, funnel_stage="BOFU", course_relevant=True)[0] == "P2"
    )


def test_prompt_fingerprint_changes():
    assert prompt_hash("a") == prompt_hash("a")
    assert prompt_hash("a") != prompt_hash("b")
    assert len(prompt_hash("a")) == 40
    assert load_thresholds()["status"].startswith("Đề xuất")

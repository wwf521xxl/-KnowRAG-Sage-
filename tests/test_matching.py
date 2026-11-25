"""评测匹配规则：时间区间、页码、Word 段号。"""
import pytest

from eval.run_eval import match, match_cite, parse_loc


def test_parse_loc():
    assert parse_loc("p12") == ("page", 12)
    assert parse_loc("01:23") == ("time", 83)
    assert parse_loc("第5段") == ("label", "第5段")
    assert parse_loc(None) is None


def test_video_match_uses_chunk_interval():
    gold = {"video_id": 1, "locator": "66:30"}
    cand = {"video_id": 1, "locator": "65:00", "start": 3900, "end": 4100}
    assert match(gold, cand) is True


def test_video_match_rejects_far_time():
    gold = {"video_id": 1, "locator": "10:00"}
    cand = {"video_id": 1, "locator": "40:00", "start": 2400, "end": 2600}
    assert match(gold, cand) is False


def test_match_rejects_other_document():
    gold = {"video_id": 1, "locator": "10:00"}
    cand = {"video_id": 2, "locator": "10:00", "start": 600, "end": 700}
    assert match(gold, cand) is False


def test_pdf_page_tolerance():
    gold = {"video_id": 9, "locator": "p12"}
    assert match(gold, {"video_id": 9, "locator": "p12"}) is True
    assert match(gold, {"video_id": 9, "locator": "p13"}) is True
    assert match(gold, {"video_id": 9, "locator": "p20"}) is False


def test_docx_segment_range():
    gold = {"video_id": 21, "locator": "第30段"}
    cand = {"video_id": 21, "locator": "第29段", "seq_start": 28, "seq_end": 30}
    assert match(gold, cand) is True
    far = {"video_id": 21, "locator": "第1段", "seq_start": 0, "seq_end": 2}
    assert match(gold, far) is False


def test_citation_tolerance_is_wider():
    gold = {"video_id": 1, "locator": "10:00"}
    cite = {"video_id": 1, "locator": "12:00"}  # 差 120 秒
    assert match_cite(gold, cite, 180) is True
    assert match_cite(gold, cite, 90) is False

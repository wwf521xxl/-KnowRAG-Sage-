"""切块逻辑：不跨文档、约 500 字、带 1 句重叠。"""
import kb_server as kb


def make_rows(n, text_len=200, video_id=1, locator=None):
    rows = []
    for i in range(n):
        rows.append({
            "video_id": video_id,
            "seq": i,
            "start": i * 10.0,
            "end": i * 10.0 + 8.0,
            "text": "字" * text_len,
            "locator": locator if locator is not None else f"{i:02d}:00",
            "embedding": None,
        })
    return rows


def test_chunks_do_not_cross_documents():
    """一份文档的句子只会拼进它自己的块。"""
    rows = make_rows(4, video_id=7)
    chunks = kb._chunk_doc(rows)
    assert chunks, "应当产生至少一个块"
    assert all(c["video_id"] == 7 for c in chunks)


def test_chunk_accumulates_until_threshold():
    """200 字一句，累计到 >=500 字才切块。"""
    rows = make_rows(5, text_len=200)
    chunks = kb._chunk_doc(rows)
    assert len(chunks) >= 2
    # 第一块由 3 句组成（200*3=600 >= 500）
    assert chunks[0]["seq_start"] == 0
    assert chunks[0]["seq_end"] == 2


def test_chunk_keeps_locator_of_first_sentence():
    rows = make_rows(3, text_len=300, locator="第1段")
    chunks = kb._chunk_doc(rows)
    assert chunks[0]["locator"] == "第1段"


def test_single_short_document_produces_one_chunk():
    rows = make_rows(1, text_len=50)
    chunks = kb._chunk_doc(rows)
    assert len(chunks) == 1
    assert chunks[0]["seq_start"] == 0 == chunks[0]["seq_end"]

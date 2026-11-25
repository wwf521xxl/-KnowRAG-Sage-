"""鉴权：签名 token 的生成、校验与篡改检测。"""
import kb_server as kb


def test_token_roundtrip():
    token = kb.make_token("boss")
    assert kb.check_token(token) == "boss"


def test_tampered_token_rejected():
    token = kb.make_token("boss")
    bad = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert kb.check_token(bad) is None


def test_garbage_token_rejected():
    assert kb.check_token("not-a-token") is None
    assert kb.check_token("") is None


def test_wrong_password_rejected():
    assert kb.verify_password("boss", "definitely-wrong-password") is False
    assert kb.verify_password("someone-else", "whatever") is False

"""Guardrails for the HOSTED (HTTP, Cloudflare-tunneled) server: read_docs must not be usable for SSRF, and
get_workflow must not read files outside the allowed workflows dir. Both matter only once the server is exposed
to external agents; offline-testable (literal IPs, no DNS needed for the block cases)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aivfx_mcp"))
import core


def test_ssrf_blocks_internal_and_bad_schemes():
    for bad in ("http://127.0.0.1:6333/x", "http://169.254.169.254/latest/meta-data",
                "http://10.0.0.5/", "http://192.168.1.1/", "https://[::1]/",
                "file:///etc/passwd", "ftp://example.com/", "not a url", ""):
        assert core._safe_public_url(bad) is False, bad


def test_ssrf_allows_public_ip():
    assert core._safe_public_url("http://8.8.8.8/") is True       # literal public ip, no DNS needed
    assert core._safe_public_url("https://1.1.1.1/doc") is True


def test_get_text_refuses_internal_url():
    import pytest
    with pytest.raises(ValueError):
        core._get_text("http://127.0.0.1:6333/collections")


def test_read_docs_flags_blocked_url():
    # default http_get (_get_text) raises on the internal url -> read_docs returns empty text + an error flag
    out = core.read_docs("http://localhost:6333/x")
    assert out["text"] == "" and out.get("error")


def test_workflow_path_safety(tmp_path, monkeypatch):
    root = tmp_path / "workflows"; root.mkdir()
    good = root / "wf.json"; good.write_text('{"ok":1}', encoding="utf-8")
    outside = tmp_path / "secret.txt"; outside.write_text("top secret", encoding="utf-8")
    monkeypatch.setattr(core, "WORKFLOWS_ROOT", str(root))
    content, err = core._read_workflow_file(str(good))
    assert err is None and content == '{"ok":1}'
    content, err = core._read_workflow_file(str(outside))
    assert content is None and err and "outside" in err


def test_workflow_no_restriction_when_root_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "WORKFLOWS_ROOT", "")   # back-compat: stdio/local use, path from trusted payload
    f = tmp_path / "wf.json"; f.write_text('{"a":1}', encoding="utf-8")
    content, err = core._read_workflow_file(str(f))
    assert err is None and content == '{"a":1}'

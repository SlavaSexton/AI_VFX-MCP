# Workflows + Attach-file - Plan B (AI_VFX-MCP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The MCP exposes workflow files attached by Plan A to AI agents - `search_feed`/`latest` items surface `has_workflow`, and a new `get_workflow(post_id|query)` tool returns the file's content.

**Architecture:** `core.py` maps Qdrant payloads to items and runs semantic search; deps (embed/Qdrant/file-read) are injected for offline tests. Plan A wrote `has_workflow`/`workflow_file`/`workflow_path`(abs)/`workflow_tg_url` into the post's `published_posts` Qdrant payload. We (Task 1) expose `id` + the workflow flag/name/url on items, and (Task 2) add `get_workflow` (resolve a point by id or query → read `workflow_path` from disk → return content; binary/too-large → `tg_url` fallback) plus its `server.py` tool.

**Tech Stack:** Python, FastMCP (`aivfx_mcp/server.py`), Qdrant HTTP (`published_posts`), pytest (deps injected - offline, no live Qdrant/Ollama).

**Spec:** `D:\n8n\projects\telegram-agent\docs\superpowers\specs\2026-06-12-workflows-attach-file-design.md` (Part B). Repo: `D:\n8n\projects\AI_VFX-MCP`. Run tests: `cd /d/n8n/projects/AI_VFX-MCP && python -m pytest -q`.

## File Structure

| Файл | Роль |
|---|---|
| Modify `aivfx_mcp/core.py` | `item_from_point` +id/workflow fields; `qdrant_get_default`; `_read_workflow_file`; `get_workflow` |
| Modify `aivfx_mcp/server.py` | `@mcp.tool() get_workflow` |
| Modify `tests/test_core.py` | tests for both |

---

### Task 1: `item_from_point` exposes `id` + workflow fields

**Files:** Modify `aivfx_mcp/core.py` (`item_from_point`, ~line 46-68); Modify `tests/test_core.py` (append).

- [ ] **Step 1: Append tests** to `tests/test_core.py`:
```python
def test_item_from_point_exposes_id_and_workflow():
    it = core.item_from_point({"id": "u9", "payload": {
        "title": "T", "has_workflow": True, "workflow_file": "f.json",
        "workflow_tg_url": "https://t.me/AI_VFX_NEWS/9"}})
    assert it["id"] == "u9" and it["has_workflow"] is True
    assert it["workflow_file"] == "f.json" and it["workflow_tg_url"].endswith("/9")


def test_item_from_point_workflow_defaults():
    it = core.item_from_point({"id": "u", "payload": {"title": "Bare"}})
    assert it["has_workflow"] in (None, False) and it["workflow_file"] is None
    assert it["workflow_tg_url"] is None
```

- [ ] **Step 2:** Run `cd /d/n8n/projects/AI_VFX-MCP && python -m pytest tests/test_core.py -q -k "exposes_id or workflow_defaults"` → FAIL (KeyError 'id'/'has_workflow').

- [ ] **Step 3:** In `aivfx_mcp/core.py`, in `item_from_point`, add four keys to the returned dict (right before the existing `"score": ...` line):
```python
        "id": p.get("id"),
        "has_workflow": pl.get("has_workflow"),
        "workflow_file": pl.get("workflow_file"),
        "workflow_tg_url": pl.get("workflow_tg_url"),
        "score": round(p.get("score", 0) or 0, 3),
```
(Keep the existing `"score"` line - just insert the four keys before it. Do not change any other mapping.)

- [ ] **Step 4:** Run `python -m pytest tests/test_core.py -q` → expect all pass (the 2 new + all existing; the pre-existing item_from_point tests check specific fields, not exact dict equality, so they still pass).

- [ ] **Step 5: Commit** (exactly these 2 files):
```bash
cd /d/n8n/projects/AI_VFX-MCP && git add aivfx_mcp/core.py tests/test_core.py && git commit -m "feat(mcp): item_from_point exposes id + has_workflow/workflow_file/workflow_tg_url" --no-verify
```

---

### Task 2: `get_workflow` tool

**Files:** Modify `aivfx_mcp/core.py` (add `qdrant_get_default`, `_read_workflow_file`, `get_workflow`); Modify `aivfx_mcp/server.py`; Modify `tests/test_core.py` (append).

- [ ] **Step 1: Append tests** to `tests/test_core.py`:
```python
def test_get_workflow_by_post_id_returns_content():
    pt = {"id": "u1", "payload": {"has_workflow": True, "workflow_path": "/w/f.json",
          "workflow_file": "f.json", "workflow_tg_url": "https://t.me/AI_VFX_NEWS/9", "title": "Relight"}}
    out = core.get_workflow(post_id="u1", qdrant_get=lambda i: pt if i == "u1" else None,
                            read_file=lambda p: ('{"node":1}', None))
    assert out["filename"] == "f.json" and out["content"] == '{"node":1}'
    assert out["tg_url"].endswith("/9") and out["post_title"] == "Relight"


def test_get_workflow_by_query_picks_first_with_workflow():
    pts = [{"id": "a", "payload": {"title": "no wf"}},
           {"id": "b", "payload": {"has_workflow": True, "workflow_path": "/w/b.json",
            "workflow_file": "b.json", "workflow_tg_url": "u", "title": "WF"}}]
    out = core.get_workflow(query="relight", embed=lambda t: [0.1],
                            qdrant_search=lambda v, k: pts, read_file=lambda p: ("CONTENT", None))
    assert out["content"] == "CONTENT" and out["filename"] == "b.json"


def test_get_workflow_no_post():
    assert "error" in core.get_workflow(post_id="x", qdrant_get=lambda i: None)


def test_get_workflow_post_without_workflow():
    pt = {"id": "u", "payload": {"title": "plain"}}
    out = core.get_workflow(post_id="u", qdrant_get=lambda i: pt, read_file=lambda p: ("x", None))
    assert "error" in out and "no workflow" in out["error"].lower()


def test_get_workflow_binary_or_large_falls_back_to_tg_url():
    pt = {"id": "u", "payload": {"has_workflow": True, "workflow_path": "/w/big.bin",
          "workflow_file": "big.bin", "workflow_tg_url": "https://t.me/AI_VFX_NEWS/12", "title": "Big"}}
    out = core.get_workflow(post_id="u", qdrant_get=lambda i: pt, read_file=lambda p: (None, "too large"))
    assert "content" not in out and out["error"] == "too large" and out["tg_url"].endswith("/12")


def test_read_workflow_file_real(tmp_path):
    p = tmp_path / "f.json"; p.write_text('{"a":1}', encoding="utf-8")
    c, e = core._read_workflow_file(str(p)); assert c == '{"a":1}' and e is None
    c, e = core._read_workflow_file(str(tmp_path / "missing")); assert c is None and e
    big = tmp_path / "big"; big.write_bytes(b"x" * 100)
    c, e = core._read_workflow_file(str(big), max_chars=10); assert c is None and "large" in e
    binf = tmp_path / "b.bin"; binf.write_bytes(b"\xff\xfe\x00\x01")
    c, e = core._read_workflow_file(str(binf)); assert c is None and "binary" in e.lower()
```

- [ ] **Step 2:** Run `python -m pytest tests/test_core.py -q -k "get_workflow or read_workflow"` → FAIL (`AttributeError: module 'aivfx_mcp.core' has no attribute 'get_workflow'`).

- [ ] **Step 3a:** In `aivfx_mcp/core.py`, add after `qdrant_scroll_default` (the other qdrant helpers, ~line 44):
```python
def qdrant_get_default(point_id):
    """Retrieve one point (with payload) by its Qdrant id - used to fetch a specific post's workflow."""
    res = _post(f"{QDRANT_URL}/collections/{COLLECTION}/points",
                {"ids": [point_id], "with_payload": True}, 20)
    pts = res.get("result") or []
    return pts[0] if pts else None
```

- [ ] **Step 3b:** Add the file reader + tool (place after `latest`, ~line 76):
```python
def _read_workflow_file(path, max_chars=262144):
    """Read a workflow file as text for inlining to the agent. Returns (content, None) or (None, error).
    Missing/too-large/binary -> error string (the caller falls back to the Telegram download link)."""
    try:
        with open(path, "rb") as f:
            data = f.read(max_chars + 1)
    except Exception:
        return None, "file not found on the feed host"
    if len(data) > max_chars:
        return None, f"file too large to inline ({max_chars}+ bytes) - download from Telegram"
    try:
        return data.decode("utf-8"), None
    except Exception:
        return None, "binary file - download from Telegram"


def get_workflow(post_id="", query="", *, embed=embed_ollama, qdrant_search=qdrant_search_default,
                 qdrant_get=qdrant_get_default, read_file=_read_workflow_file):
    """Fetch the workflow file attached to a feed post. Resolve the post by Qdrant point id (post_id - an
    item's 'id' from search_feed/latest) OR by semantic query (first matching post that has a workflow), read
    its file from the feed host, and return {filename, content, tg_url, post_title}. If the file can't be
    inlined (binary / too large / missing) returns {error, filename, tg_url, post_title} so the agent can
    download it from Telegram instead."""
    point = None
    if post_id:
        point = qdrant_get(post_id)
    elif query:
        for p in qdrant_search(embed(query), 8):
            pl = p.get("payload") or {}
            if pl.get("has_workflow") and pl.get("workflow_path"):
                point = p
                break
    if not point:
        return {"error": "no matching post found"}
    pl = point.get("payload") or {}
    if not (pl.get("has_workflow") and pl.get("workflow_path")):
        return {"error": "this post has no workflow attached", "post_title": pl.get("title")}
    content, err = read_file(pl["workflow_path"])
    out = {"filename": pl.get("workflow_file"), "tg_url": pl.get("workflow_tg_url"),
           "post_title": pl.get("title")}
    if err:
        out["error"] = err
    else:
        out["content"] = content
    return out
```

- [ ] **Step 3c:** In `aivfx_mcp/server.py`, add a tool after `read_docs` (before `def main()`):
```python
@mcp.tool()
def get_workflow(post_id: str = "", query: str = "") -> dict:
    """Download the workflow file attached to a feed post (e.g. a ComfyUI/n8n JSON the editor attached when
    it isn't available online). Pass post_id (an item's 'id' from search_feed/latest) or a query. Returns
    {filename, content, tg_url, post_title}; if the file can't be inlined (binary/too large) returns
    {error, tg_url, ...} to download from Telegram."""
    return core.get_workflow(post_id=post_id, query=query)
```

- [ ] **Step 4:** Run `python -m pytest tests/test_core.py -q` → expect all pass. Parse-check server: `python -c "import ast; ast.parse(open('aivfx_mcp/server.py',encoding='utf-8').read()); print('ok')"`.

- [ ] **Step 5: FULL suite.** `cd /d/n8n/projects/AI_VFX-MCP && python -m pytest -q` → all passed.

- [ ] **Step 6: Commit** (exactly these 3 files):
```bash
git add aivfx_mcp/core.py aivfx_mcp/server.py tests/test_core.py && git commit -m "feat(mcp): get_workflow tool - return attached workflow file content (by post_id or query)" --no-verify
```

---

## Деплой (владелец)
MCP перезапускается своим способом (stdio-сервер запускается агентом/клиентом - перезапусти MCP-клиент/сессию). Стор `ROOT/workflows/` пишет Plan A; MCP читает `workflow_path` из Qdrant-payload и отдаёт содержимое. Ретеншн `workflows/` - на будущее (файлы не чистятся на happy-path).

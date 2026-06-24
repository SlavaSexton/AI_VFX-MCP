"""Core logic for the AI VFX feed MCP, kept free of any transport so it is unit-testable.

The pipeline (telegram-agent) indexes every published post into Qdrant with a payload that already carries the
resolved artifacts (github, hf_model, hf_quants, license, model_size_gb, arxiv). This module:
  - embeds a query (Ollama nomic-embed-text, 768d) and runs a semantic search over that collection,
  - maps each hit to a clean item,
  - turns an item's artifacts into a ready-to-run install plan that a consuming agent can execute.

External dependencies (embedding, Qdrant) are injected so the logic can be tested offline. The defaults talk to a
local Ollama + Qdrant; override via env (OLLAMA_URL, QDRANT_URL, FEED_COLLECTION, EMBED_MODEL)."""
import os, re, json, html, socket, ipaddress, urllib.request, urllib.parse

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("FEED_COLLECTION", "published_posts")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
WORKFLOWS_ROOT = os.environ.get("WORKFLOWS_ROOT", "")   # if set, get_workflow only reads files under this dir (hosted path-safety)


def _post(url, body, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def embed_ollama(text):
    """768d embedding via local Ollama (same model the pipeline indexes with)."""
    res = _post(f"{OLLAMA_URL}/api/embeddings", {"model": EMBED_MODEL, "prompt": text}, 30)
    return res.get("embedding") or []


def qdrant_search_default(vector, top_k):
    """Cosine search over the published-posts collection. Returns Qdrant point dicts."""
    res = _post(f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                {"vector": vector, "limit": top_k, "with_payload": True}, 20)
    return res.get("result") or []


def qdrant_scroll_default(limit):
    res = _post(f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll",
                {"limit": limit, "with_payload": True}, 20)
    return (res.get("result") or {}).get("points") or []


def qdrant_get_default(point_id):
    """Retrieve one point (with payload) by its Qdrant id - used to fetch a specific post's workflow."""
    res = _post(f"{QDRANT_URL}/collections/{COLLECTION}/points",
                {"ids": [point_id], "with_payload": True}, 20)
    pts = res.get("result") or []
    return pts[0] if pts else None


def item_from_point(p):
    """Map a Qdrant hit to a clean, agent-friendly item."""
    pl = p.get("payload") or {}
    return {
        "title": pl.get("title"),
        "summary": pl.get("summary") or pl.get("desc"),
        "category": pl.get("category"),
        "date": pl.get("date"),
        "source_url": pl.get("source_url") or pl.get("url"),
        "tg_url": pl.get("tg_url"),
        "github": pl.get("github"),
        "hf_model": pl.get("hf_model"),
        "hf_quants": pl.get("hf_quants") or [],
        "license": pl.get("license"),
        "model_size_gb": pl.get("model_size_gb"),
        "arxiv": pl.get("arxiv"),
        "id": p.get("id"),
        "has_workflow": pl.get("has_workflow"),
        "workflow_file": pl.get("workflow_file"),
        "workflow_tg_url": pl.get("workflow_tg_url"),
        "score": round(p.get("score", 0) or 0, 3),
    }


def search_feed(query, top_k=8, *, embed=embed_ollama, qdrant_search=qdrant_search_default):
    """Semantic search over the feed. Returns clean items (the same results the search bot serves)."""
    vector = embed(query)
    return [item_from_point(p) for p in qdrant_search(vector, top_k)]


def latest(n=10, *, qdrant_scroll=qdrant_scroll_default):
    """Most recent items by date (newest first)."""
    items = [item_from_point(p) for p in qdrant_scroll(n * 3)]
    items = [it for it in items if it.get("date")]
    items.sort(key=lambda it: it["date"], reverse=True)
    return items[:n]


def _read_workflow_file(path, max_chars=262144):
    """Read a workflow file as text for inlining to the agent. Returns (content, None) or (None, error).
    Missing/too-large/binary -> error string (the caller falls back to the Telegram download link).
    When WORKFLOWS_ROOT is set (a hosted server), the path MUST resolve under it, so a payload can only point
    at a real workflow file, never an arbitrary path on the host."""
    if WORKFLOWS_ROOT:
        try:
            root = os.path.realpath(WORKFLOWS_ROOT)
            if os.path.commonpath([root, os.path.realpath(path)]) != root:
                return None, "workflow path outside the allowed directory"
        except Exception:
            return None, "invalid workflow path"
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


def _hf_id(url_or_id):
    if not url_or_id:
        return None
    return url_or_id.split("huggingface.co/")[-1].rstrip("/")


def _safe_public_url(url):
    """True only for an http(s) URL whose host resolves to a PUBLIC ip. Blocks SSRF: a user passing
    http://localhost:6333, http://169.254.169.254 (cloud metadata), or a private-LAN address to make this
    server fetch internal services. Used before every server-side fetch in read_docs."""
    try:
        u = urllib.parse.urlparse(url or "")
    except Exception:
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return bool(infos)


def _get_text(url, timeout=20):
    if not _safe_public_url(url):
        raise ValueError("blocked: non-public or invalid URL")
    req = urllib.request.Request(url, headers={"User-Agent": "ai-vfx-mcp"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _strip_html(s):
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', s)
    s = re.sub(r'(?s)<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n\s*\n\s*\n+', '\n\n', s)
    return s.strip()


def _looks_html(s):
    return bool(re.search(r'(?i)<html|<body|<div|<p[ >]|<head', s))


def read_docs(url, max_chars=20000, *, http_get=_get_text):
    """Fetch readable documentation text for a URL so an agent can implement from it when no runnable repo exists.
    GitHub/HF resolve to the raw README/model-card; other pages are fetched and stripped of HTML. Consumer-side
    only - this never feeds the pipeline's writer model."""
    targets = [url]
    mg = re.search(r'github\.com/([^/\s]+)/([^/\s#?]+)', url or "")
    mh = re.search(r'huggingface\.co/([^\s#?]+)', url or "")
    if mg:
        o, r = mg.group(1), mg.group(2)
        targets = [f"https://raw.githubusercontent.com/{o}/{r}/main/README.md",
                   f"https://raw.githubusercontent.com/{o}/{r}/master/README.md"]
    elif mh:
        rid = mh.group(1).rstrip("/")
        targets = [f"https://huggingface.co/{rid}/raw/main/README.md",
                   f"https://huggingface.co/{rid}/raw/master/README.md"]
    text, used = "", url
    for t in targets:
        try:
            body = http_get(t) or ""
        except Exception:
            body = ""
        if body.strip():
            text, used = body, t
            break
    if _looks_html(text):
        text = _strip_html(text)
    text = text.strip()[:max_chars]
    out = {"url": url, "source": used, "text": text, "chars": len(text)}
    if not text and not _safe_public_url(url):
        out["error"] = "blocked: non-public or invalid URL"
    return out


def install_plan(item):
    """Ready-to-run fetch commands for an item's artifacts. The CONSUMING agent runs these (under its own
    sandbox/approval rules) - this only hands over the exact commands."""
    cmds = []
    if item.get("github"):
        cmds.append({"type": "git", "cmd": f"git clone {item['github']}", "target": item["github"]})
    if item.get("hf_model"):
        mid = _hf_id(item["hf_model"])
        if mid:
            cmds.append({"type": "hf-model", "cmd": f"huggingface-cli download {mid}", "target": mid,
                         "size_gb": item.get("model_size_gb"), "license": item.get("license")})
    for q in item.get("hf_quants") or []:
        qid = q.get("id") or _hf_id(q.get("url"))
        if qid:
            cmds.append({"type": "hf-quant", "cmd": f"huggingface-cli download {qid}", "target": qid,
                         "fmt": q.get("fmt")})
    return cmds

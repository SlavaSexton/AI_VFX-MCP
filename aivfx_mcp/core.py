"""Core logic for the AI VFX feed MCP, kept free of any transport so it is unit-testable.

The pipeline (telegram-agent) indexes every published post into Qdrant with a payload that already carries the
resolved artifacts (github, hf_model, hf_quants, license, model_size_gb, arxiv). This module:
  - embeds a query (Ollama nomic-embed-text, 768d) and runs a semantic search over that collection,
  - maps each hit to a clean item,
  - turns an item's artifacts into a ready-to-run install plan that a consuming agent can execute.

External dependencies (embedding, Qdrant) are injected so the logic can be tested offline. The defaults talk to a
local Ollama + Qdrant; override via env (OLLAMA_URL, QDRANT_URL, FEED_COLLECTION, EMBED_MODEL)."""
import os, json, urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("FEED_COLLECTION", "published_posts")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")


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


def _hf_id(url_or_id):
    if not url_or_id:
        return None
    return url_or_id.split("huggingface.co/")[-1].rstrip("/")


def install_plan(item):
    """Ready-to-run fetch commands for an item's artifacts. The CONSUMING agent runs these (under its own
    sandbox/approval rules) — this only hands over the exact commands."""
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

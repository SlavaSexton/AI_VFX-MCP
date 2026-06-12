"""Core of the AI VFX feed MCP: semantic search over the published-posts archive and a ready-to-run install plan
for the code/model artifacts each item carries. All external deps (embedding, Qdrant) are injected so tests are
offline."""
from aivfx_mcp import core


def _point(payload, score=0.9):
    return {"id": "p1", "score": score, "payload": payload}


def test_item_from_point_maps_artifacts():
    it = core.item_from_point(_point({
        "title": "HunyuanVideo", "summary": "open video model", "category": "VideoGen", "date": "2026-06-06",
        "source_url": "https://aivideo.tencent.com", "tg_url": "https://t.me/AI_VFX_NEWS/123",
        "github": "https://github.com/Tencent/HunyuanVideo", "hf_model": "https://huggingface.co/tencent/HunyuanVideo",
        "hf_quants": [{"id": "city96/HunyuanVideo-gguf", "fmt": "GGUF"}],
        "license": "other", "model_size_gb": 6.0, "arxiv": "2412.03603"}))
    assert it["title"] == "HunyuanVideo"
    assert it["github"] == "https://github.com/Tencent/HunyuanVideo"
    assert it["hf_model"] == "https://huggingface.co/tencent/HunyuanVideo"
    assert it["hf_quants"][0]["fmt"] == "GGUF"
    assert it["license"] == "other" and it["model_size_gb"] == 6.0
    assert it["tg_url"].endswith("/123")
    assert it["score"] == 0.9


def test_item_from_point_defaults_missing_fields():
    it = core.item_from_point(_point({"title": "Bare"}))
    assert it["title"] == "Bare"
    assert it["github"] is None and it["hf_model"] is None
    assert it["hf_quants"] == []


def test_search_feed_embeds_query_and_returns_items():
    seen = {}
    def fake_embed(text):
        seen["q"] = text
        return [0.1, 0.2, 0.3]
    def fake_qdrant(vector, top_k):
        seen["vec"], seen["k"] = vector, top_k
        return [_point({"title": "Genie 3", "github": "https://github.com/deepmind/genie3"}, score=0.81)]
    items = core.search_feed("world models", top_k=5, embed=fake_embed, qdrant_search=fake_qdrant)
    assert seen["q"] == "world models"
    assert seen["vec"] == [0.1, 0.2, 0.3] and seen["k"] == 5
    assert items[0]["title"] == "Genie 3"
    assert items[0]["github"] == "https://github.com/deepmind/genie3"


def test_install_plan_builds_git_and_hf_commands():
    plan = core.install_plan({
        "github": "https://github.com/Tencent/HunyuanVideo",
        "hf_model": "https://huggingface.co/tencent/HunyuanVideo",
        "hf_quants": [{"id": "city96/HunyuanVideo-gguf", "fmt": "GGUF"}]})
    cmds = [c["cmd"] for c in plan]
    assert "git clone https://github.com/Tencent/HunyuanVideo" in cmds
    assert "huggingface-cli download tencent/HunyuanVideo" in cmds
    assert "huggingface-cli download city96/HunyuanVideo-gguf" in cmds


def test_install_plan_empty_without_artifacts():
    assert core.install_plan({"title": "news only, no code"}) == []


# ---------- read_docs: fetch readable text so an agent can implement when there's no repo ----------

class FakeGet:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []
    def __call__(self, url, timeout=20):
        self.calls.append(url)
        for frag, resp in self.routes.items():
            if frag in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return ""


def test_read_docs_github_returns_readme():
    g = FakeGet({"raw.githubusercontent.com": "# Proj\nInstall and run it."})
    d = core.read_docs("https://github.com/o/r", http_get=g)
    assert "Install and run it." in d["text"]
    assert "README" in d["source"]


def test_read_docs_hf_returns_model_card():
    g = FakeGet({"huggingface.co": "# Model\nUse with diffusers."})
    d = core.read_docs("https://huggingface.co/org/model", http_get=g)
    assert "diffusers" in d["text"]
    assert "raw/main/README" in d["source"]


def test_read_docs_strips_html_for_generic_page():
    g = FakeGet({"example.com": "<html><head><style>x{}</style></head><body><h1>Title</h1><p>Body &amp; more</p></body></html>"})
    d = core.read_docs("https://example.com/docs", http_get=g)
    assert "Title" in d["text"] and "Body & more" in d["text"]
    assert "<" not in d["text"]


def test_read_docs_truncates_to_max_chars():
    g = FakeGet({"example.com": "A" * 5000})
    d = core.read_docs("https://example.com/x", max_chars=100, http_get=g)
    assert len(d["text"]) <= 100


def test_read_docs_github_falls_back_to_master():
    g = FakeGet({"/main/README.md": ValueError("404"), "/master/README.md": "# Old\nlegacy build"})
    d = core.read_docs("https://github.com/o/r", http_get=g)
    assert "legacy build" in d["text"]
    assert "master" in d["source"]


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

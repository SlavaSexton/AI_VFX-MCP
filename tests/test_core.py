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

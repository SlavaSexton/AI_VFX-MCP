"""MCP server (stdio) exposing the AI VFX feed to any MCP-capable agent: Claude, Gemini, Codex, etc.

Thin adapter over core.py + coderesolve.py. Run it directly (`python -m aivfx_mcp.server`) or via the console
script `aivfx-mcp`. Configuration is by env (OLLAMA_URL, QDRANT_URL, FEED_COLLECTION, GITHUB_TOKEN)."""
from . import core, coderesolve

try:
    from mcp.server.fastmcp import FastMCP
except Exception as e:                                      # pragma: no cover - import guard for a clearer message
    raise SystemExit("The 'mcp' package is required. Install with: pip install mcp") from e

mcp = FastMCP("ai-vfx-feed")


@mcp.tool()
def search_feed(query: str, top_k: int = 8) -> list:
    """Semantic search over the AI VFX news archive. Returns items with title, summary, source/Telegram links,
    and the resolved code artifacts (github, hf_model, hf_quants, license, model_size_gb, arxiv)."""
    return core.search_feed(query, top_k)


@mcp.tool()
def latest(n: int = 10) -> list:
    """Most recent items from the feed (newest first), with the same fields as search_feed."""
    return core.latest(n)


@mcp.tool()
def install_plan(github: str = "", hf_model: str = "", hf_quants: list | None = None) -> list:
    """Turn an item's artifacts into ready-to-run fetch commands (git clone / huggingface-cli download).
    The CALLING agent executes them under its own sandbox/approval rules."""
    return core.install_plan({"github": github or None, "hf_model": hf_model or None,
                              "hf_quants": hf_quants or []})


@mcp.tool()
def resolve_artifacts(name: str, text: str = "") -> dict:
    """On-demand resolver for an item whose artifacts were not pre-resolved: find the GitHub repo, the Hugging
    Face model (license/size) and its quantizations, and arXiv -> code. Returns the same shape stored in the feed."""
    return coderesolve.resolve(name, text)


@mcp.tool()
def read_docs(url: str, max_chars: int = 20000) -> dict:
    """Fetch readable documentation text for a URL (GitHub/HF README, arXiv, docs page) so the agent can
    implement a technique even when there is no runnable repo. Returns {url, source, text, chars}."""
    return core.read_docs(url, max_chars)


@mcp.tool()
def get_workflow(post_id: str = "", query: str = "") -> dict:
    """Download the workflow file attached to a feed post (e.g. a ComfyUI/n8n JSON the editor attached when
    it isn't available online). Pass post_id (an item's 'id' from search_feed/latest) or a query. Returns
    {filename, content, tg_url, post_title}; if the file can't be inlined (binary/too large) returns
    {error, tg_url, ...} to download from Telegram."""
    return core.get_workflow(post_id=post_id, query=query)


def main():
    mcp.run()


def main_http():
    """Serve the feed over streamable-http on localhost, for a remote (Cloudflare-tunneled) MCP. Binds 127.0.0.1
    so ONLY the local tunnel client can reach it, never the LAN. Env: MCP_HOST, MCP_PORT (default 8787).
    Keep WORKFLOWS_ROOT set so get_workflow stays path-restricted, and put rate-limiting at the Cloudflare edge."""
    import os
    mcp.settings.host = os.environ.get("MCP_HOST", "127.0.0.1")
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8787"))
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()

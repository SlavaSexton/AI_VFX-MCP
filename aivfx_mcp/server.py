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


def main():
    mcp.run()


if __name__ == "__main__":
    main()

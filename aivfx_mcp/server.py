"""MCP server (stdio) exposing the AI VFX feed to any MCP-capable agent: Claude, Gemini, Codex, etc.

Thin adapter over core.py + coderesolve.py. Run it directly (`python -m aivfx_mcp.server`) or via the console
script `aivfx-mcp`. Configuration is by env (OLLAMA_URL, QDRANT_URL, FEED_COLLECTION, GITHUB_TOKEN)."""
from . import core, coderesolve

try:
    from mcp.server.mcpserver import MCPServer
except ImportError as e:                                    # pragma: no cover - import guard for a clearer message
    # RESPONSIBLE FOR: SDK v2 migration (2026-07-29). The 2026-07-28 spec renamed FastMCP to
    # MCPServer and removed mcp.server.fastmcp, so a 1.x install lands here. Name the actual
    # problem: the old guard claimed "the package is required" even when mcp WAS installed.
    try:
        from importlib.metadata import version as _v
        _installed = _v("mcp")
    except Exception:
        _installed = None
    if _installed:
        raise SystemExit(
            f"Installed 'mcp' is {_installed}, which predates the 2026-07-28 spec (no mcp.server.mcpserver).\n"
            f"This server targets the v2 SDK. Upgrade with:  pip install 'mcp>=2.0'"
        ) from e
    raise SystemExit("The 'mcp' package is required. Install with: pip install 'mcp>=2.0'") from e

# version flows from __init__ so serverInfo stops reporting an empty string to clients
# (v2 added version to the MCPServer constructor; an unversioned server reports "").
from . import __version__ as _pkg_version

mcp = MCPServer("ai-vfx-feed", version=_pkg_version)


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
    so ONLY the local tunnel client can reach it, never the LAN. Env: MCP_HOST, MCP_PORT (default 8787),
    MCP_ALLOWED_HOSTS (comma-separated public hostnames the tunnel serves under), MCP_STATELESS=1 to opt
    into the 2026-07-28 stateless transport (any request may land on any instance; no session state).
    Keep WORKFLOWS_ROOT set so get_workflow stays path-restricted, and put rate-limiting at the Cloudflare edge."""
    import os
    from mcp.server.transport_security import TransportSecuritySettings
    # Behind a tunnel the Host header is the PUBLIC hostname, not 127.0.0.1, so the SDK's default
    # localhost-only DNS-rebinding guard 421s every tunneled request. With a fixed domain (named
    # tunnel) pin it via MCP_ALLOWED_HOSTS and keep the guard ON; with an ephemeral quick tunnel
    # (random *.trycloudflare.com each run) there is no stable host to pin, so disable the host
    # check -- safe here because the origin binds 127.0.0.1 (only the local cloudflared client
    # reaches it) and the feed is read-only.  RESPONSIBLE FOR: tunneled-host 421 fix (2026-06-24).
    allowed = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if allowed:
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=allowed, allowed_origins=allowed)
    else:
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    # RESPONSIBLE FOR: SDK v2 migration (2026-07-29). v2 moved every transport parameter off the
    # constructor / mcp.settings and onto run(); mcp.settings now holds only debug, log_level and
    # the duplicate-warning flags, so the old `mcp.settings.host = ...` would silently no-op.
    # stateless_http is the 2026-07-28 spec's headline mode and this server is a read-only tool
    # server (no sampling / elicitation / roots), so it has no back-channel to lose. It stays
    # OPT-IN via MCP_STATELESS so the tunneled production instance keeps its current behaviour
    # until the owner flips it deliberately.
    stateless = os.environ.get("MCP_STATELESS", "0") == "1"
    mcp.run(
        transport="streamable-http",
        host=os.environ.get("MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MCP_PORT", "8787")),
        transport_security=security,
        stateless_http=stateless,
    )


if __name__ == "__main__":
    main()

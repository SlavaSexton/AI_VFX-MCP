# Changelog

All notable changes to **AI VFX NEWS - MCP** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/).
Dates are YYYY-MM-DD. The raw, per-commit history lives in git; this file is the curated summary.

## [Unreleased]

## [0.2.0] - 2026-07-29

Moves the server onto the **2026-07-28** MCP specification, and fixes a breakage that landed the moment that
spec shipped.

### Fixed
- **A fresh install was broken.** The dependency was declared `mcp>=1.2.0` with no upper bound, so once the new
  spec shipped a bare `pip install` resolved to Python SDK **2.0.0**, which removed `mcp.server.fastmcp`, and
  every new install died on the first import. Already-running instances were unaffected, which is what kept it
  quiet. Fixed by pinning, then by migrating (below).
- **The import guard lied.** It reported "The 'mcp' package is required" even when `mcp` WAS installed and the
  real problem was a major-version mismatch. It now reads the installed version and names the actual case.
- **`serverInfo` reported an empty version** to every client. The server version now flows from the package.

### Changed
- **Migrated to the MCP Python SDK v2** (`mcp>=2.0`). `FastMCP` became `MCPServer` and the import moved to
  `mcp.server.mcpserver`. The decorator API is unchanged, so all six tools are untouched.
- **Transport configuration moved to `run()`.** v2 took every transport parameter off the constructor and off
  `mcp.settings`, which now holds only `debug`, `log_level` and the duplicate-warning flags. The old
  `mcp.settings.host = ...` assignments would have silently no-opped, so `host`, `port` and `transport_security`
  are passed to `run()` directly. The tunneled-host DNS-rebinding logic is preserved unchanged.

### Added
- **Stateless transport, opt-in via `MCP_STATELESS=1`.** The spec's headline mode: no handshake, no session
  header, every request self-describing, so any request can land on any instance. This server is read-only with
  no sampling, elicitation or roots, so it has no back-channel to lose. Left opt-in so the hosted instance
  changes behaviour only when that is the intent.

### Verified
- `server.py` has no test coverage (the suite covers `core.py`), so this was verified by RUNNING it, not by a
  green gate: streamable HTTP in both session and stateless modes, and stdio over the pipe, each doing a real
  `tools/list` (6 tools) and `tools/call`. The production path was exercised specifically, with the
  DNS-rebinding allowlist ON: the tunnel host is served (200) and any other Host is rejected (421).
- **Backward compatibility checked against the live server, not assumed:** a 2025-11-25 client sending the old
  `initialize` handshake still gets a correct result and a session id. Older clients need no changes.

## [0.1.0]

Initial release: a hosted MCP server exposing the AI VFX news archive to any MCP-capable agent, with six
read-only tools (`search_feed`, `latest`, `install_plan`, `resolve_artifacts`, `read_docs`, `get_workflow`),
stdio and streamable-HTTP transports, an SSRF guard on outbound fetches, and a path-restricted workflow reader.

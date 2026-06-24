<p align="center"><img src="assets/AI_Moon_Full.png" width="200" alt="AI VFX"></p>

# AI VFX Feed MCP

An MCP server that gives any AI agent live, searchable access to the **AI VFX** news pipeline (`@AI_VFX_NEWS`)
and, more importantly, to the **code and models behind each story**. A coding agent can ask "what's new in video
models" and get back not just headlines but the GitHub repo, the Hugging Face model with its license, size and
quantizations, the arXiv paper, and any attached workflow, then fetch them and try them.

It speaks the open [Model Context Protocol](https://modelcontextprotocol.io), so it works with Claude, Gemini,
Codex, or anything else that speaks MCP. API is API.

## Connect to the live feed

The feed is **hosted**. You don't install or run anything, you point your agent at one URL and start searching.
The data (the curated AI VFX archive) lives behind it and is kept fresh by the pipeline.

**Endpoint:**
```
https://mcp.aivfxnews.com/mcp
```

**Claude Code:**
```bash
claude mcp add --transport http ai-vfx-feed https://mcp.aivfxnews.com/mcp
```

**Any other MCP client** (Claude Desktop, Gemini, Codex, etc.) - bridge the remote endpoint to stdio:
```json
{
  "mcpServers": {
    "ai-vfx-feed": {
      "command": "npx",
      "args": ["mcp-remote", "https://mcp.aivfxnews.com/mcp"]
    }
  }
}
```
Clients with native remote-MCP support can take the URL directly instead of the bridge.

That is the whole setup. Once connected, the agent searches the feed, pulls the repos / models / links / workflows,
and works with them on its own.

## What you get

- **`search_feed(query, top_k=8)`** - semantic search over the published-posts archive. Each result carries
  `title`, `summary`, `source_url`, `tg_url`, and the resolved artifacts: `github`, `hf_model`, `hf_quants`,
  `license`, `model_size_gb`, `arxiv`.
- **`latest(n=10)`** - the newest items, same shape.
- **`get_workflow(post_id, query)`** - the workflow file attached to a post (e.g. a ComfyUI / n8n JSON), inlined
  when small enough, otherwise a Telegram download link.
- **`install_plan(github, hf_model, hf_quants)`** - turns an item's artifacts into ready-to-run commands
  (`git clone …`, `huggingface-cli download …`). The calling agent runs them under its own rules.
- **`resolve_artifacts(name, text)`** - on-demand resolver for items not pre-resolved: finds the GitHub repo, the
  Hugging Face model (license/size) and its quantizations, arXiv → code via Papers with Code, and a docs link.
- **`read_docs(url, max_chars=20000)`** - fetch readable text (GitHub/HF README, arXiv, docs page) so an agent can
  implement a technique even when there is no runnable repo.

## How the artifacts are found

Links already in a post win. Anything missing is resolved by name behind a confidence floor:

- **GitHub:** `api.github.com/search/repositories`, ranked by name match + stars.
- **Hugging Face:** `huggingface.co/api/models` for the model (license, file sizes) plus its quantizations
  (GGUF / AWQ / GPTQ / FP8).
- **arXiv → code:** Papers with Code, preferring the official repo.

If nothing matches confidently, the field is left empty. Better empty than wrong.

## Safety

Installing code or models from a feed means running untrusted artifacts. This server only **hands over** verified
links and exact commands; it never installs anything. Downloading and running is the consuming agent's
responsibility - inspect first, gate behind approval, run isolated, and watch model sizes against your disk/VRAM.

## License

Noncommercial use only. PolyForm Noncommercial License 1.0.0: free for personal, research, and nonprofit use;
commercial use needs a separate license from the author. See [LICENSE](LICENSE).

Built solo by Slava Sexton - part of the AI VFX autonomous pipeline.

<p align="center"><img src="assets/AI_Moon_Full.png" width="200" alt="AI VFX"></p>

<h1 align="center">AI VFX NEWS - MCP</h1>

<p align="center">
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-compatible-7C3AED" alt="MCP compatible"></a>
  <img src="https://img.shields.io/badge/license-PolyForm%20NC%201.0.0-blue" alt="License: PolyForm Noncommercial">
  <a href="https://t.me/AI_VFX_NEWS"><img src="https://img.shields.io/badge/feed-%40AI__VFX__NEWS-26A5E4?logo=telegram&logoColor=white" alt="Telegram @AI_VFX_NEWS"></a>
</p>

<p align="center">
  Live, searchable access to the <b>AI VFX</b> news feed for any AI agent, with the
  <b>code and models behind every story</b> resolved and ready to fetch.
</p>

Ask "what's new in open video models" and the agent gets back not just the headline but the GitHub repo, the
Hugging Face model with its license / size / quantizations, the arXiv paper, and any attached workflow, then
fetches them and tries them. It speaks the open [Model Context Protocol](https://modelcontextprotocol.io), so
Claude, Gemini, Codex, or anything MCP-aware can use it.

## Connect to the live feed

The feed is **hosted**. Nothing to install, no database to run, you point your agent at one URL and search. The
curated archive lives behind it and the pipeline keeps it fresh.

**Endpoint:** `https://mcp.aivfxnews.com/mcp`

**Claude Code:**
```bash
claude mcp add --transport http ai-vfx-feed https://mcp.aivfxnews.com/mcp
```

**Any other MCP client** (Claude Desktop, Gemini, Codex, and the like) bridges the remote endpoint to stdio:
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
Clients with native remote-MCP support can take the URL directly.

That is the whole setup. Once connected, the agent searches, pulls the repos / models / links / workflows, and
works with them on its own.

## What you get back

`search_feed("open source soundtrack generation")` returns clean, resolved items:

```json
{
  "title": "NJU-Speech releases open-source model for full soundtrack generation",
  "github": "https://github.com/NJU-Speech/Foley-Omni",
  "hf_model": "https://huggingface.co/CocoBro/Foley-Omni",
  "arxiv": "2606.03672",
  "tg_url": "https://t.me/AI_VFX_NEWS/1350"
}
```

`license`, `model_size_gb` and the GGUF / AWQ / GPTQ / FP8 quantizations come along too when they resolve. The
agent can then call `install_plan` for the exact `git clone` / `huggingface-cli download` commands, or
`get_workflow` to pull an attached ComfyUI / n8n graph.

## Tools

- **`search_feed(query, top_k=8)`** - semantic search over the archive; each hit carries title, summary,
  source / Telegram links and the resolved `github`, `hf_model`, `hf_quants`, `license`, `model_size_gb`, `arxiv`.
- **`latest(n=10)`** - the newest items, same shape.
- **`get_workflow(post_id, query)`** - the workflow file attached to a post (ComfyUI / n8n JSON), inlined when
  small, otherwise a Telegram download link.
- **`install_plan(github, hf_model, hf_quants)`** - turns artifacts into ready-to-run fetch commands; the calling
  agent runs them under its own rules.
- **`resolve_artifacts(name, text)`** - on-demand resolver for items not pre-resolved (GitHub, Hugging Face,
  arXiv to code).
- **`read_docs(url, max_chars=20000)`** - readable text from a GitHub / HF README, arXiv, or docs page, so an
  agent can implement a technique even when there is no runnable repo.

## How the artifacts are found

Links already in a post win. Anything missing is resolved by name behind a confidence floor: GitHub search ranked
by name + stars, the Hugging Face API for the model (license, sizes) and its quantizations, and Papers with Code
for arXiv to repo. If nothing matches confidently, the field is left empty. Better empty than wrong.

## Safety

Installing code or models from a feed means running untrusted artifacts. This server only **hands over** verified
links and exact commands, it never installs anything. Downloading and running is the consuming agent's job:
inspect first, gate behind approval, run isolated, and watch model sizes against your disk / VRAM.

## License

Noncommercial use only. PolyForm Noncommercial License 1.0.0: free for personal, research and nonprofit use;
commercial use needs a separate license from the author. See [LICENSE](LICENSE).

Built solo by Slava Sexton, part of the AI VFX autonomous pipeline.

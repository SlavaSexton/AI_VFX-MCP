"""Resolve the code/model behind a news item.

For a piece of news (a model release, a tool, a paper) this finds the canonical artifacts an agent can actually
use: the GitHub repo, the Hugging Face model (with license, size and quantizations), and the arXiv -> code link
via Papers with Code. Links already present in the post win; anything missing is resolved by name search behind a
confidence floor. Everything is meant to run at INGEST time and be stored in the post payload, so the feed itself
already carries the code/model and an offline agent only has to download.

All network access goes through an injected `http(url, headers, timeout) -> parsed JSON` so it is fully testable.
"""
import os, re, json, urllib.request, urllib.parse

CONF_MIN = 0.6                                              # below this we report nothing (better empty than wrong)
GH_API  = "https://api.github.com"
HF_API  = "https://huggingface.co/api"
PWC_API = "https://paperswithcode.com/api/v1"

_ARXIV_RE = re.compile(r'arxiv\.org/abs/(\d{4}\.\d{4,5})', re.I)
_GH_RE    = re.compile(r'github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', re.I)
_HF_RE    = re.compile(r'huggingface\.co/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)', re.I)


def _get_json(url, headers=None, timeout=20):
    h = {"User-Agent": "ai-vfx-resolver", "Accept": "application/json"}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def _name_match(query, candidate):
    """Similarity 0..1 between a wanted name and a candidate repo/model name."""
    q, c = _norm(query), _norm(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c or c in q:
        return 0.85
    qs = set(re.findall(r'[a-z0-9]+', query.lower()))
    cs = set(re.findall(r'[a-z0-9]+', candidate.lower()))
    if not qs:
        return 0.0
    return len(qs & cs) / len(qs) * 0.7


def find_code(name, *, http=_get_json, token=None):
    """Best-matching GitHub repo for a project/model name, or None below the confidence floor."""
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    q = urllib.parse.quote(name)
    try:
        res = http(f"{GH_API}/search/repositories?q={q}&sort=stars&order=desc&per_page=10", headers, 20)
    except Exception:
        return None
    best, best_conf = None, 0.0
    for it in (res or {}).get("items") or []:
        conf = _name_match(name, it.get("name", ""))
        if conf > best_conf:
            best_conf, best = conf, it
    if not best or best_conf < CONF_MIN:
        return None
    return {"url": best.get("html_url"), "full_name": best.get("full_name"),
            "stars": best.get("stargazers_count", 0), "confidence": round(best_conf, 2)}


def _tag_license(tags):
    for t in tags or []:
        if isinstance(t, str) and t.lower().startswith("license:"):
            return t.split(":", 1)[1]
    return None


def _siblings_size_gb(siblings):
    total = 0
    for s in siblings or []:
        try: total += int(s.get("size") or 0)
        except Exception: pass
    return round(total / 1_000_000_000, 2)


def _model_info(mid, http):
    try:
        return http(f"{HF_API}/models/{mid}?blobs=true", None, 20) or {}
    except Exception:
        return {}


def find_model(name, *, http=_get_json, prefer_org=None):
    """Best-matching Hugging Face model for a name, with license + size, or None below the floor.
    prefer_org (e.g. the GitHub repo owner) tie-breaks toward the OFFICIAL namespace over community mirrors."""
    q = urllib.parse.quote(name)
    try:
        res = http(f"{HF_API}/models?search={q}&sort=downloads&direction=-1&limit=10", None, 20)
    except Exception:
        return None
    scored = []
    for it in res or []:
        mid = it.get("id") or it.get("modelId") or ""
        if "/" not in mid:
            continue
        org, nm = mid.split("/", 1)
        conf = _name_match(name, nm)
        if conf < CONF_MIN:
            continue
        org_strong = 1 if (prefer_org and _name_match(prefer_org, org) >= 0.8) else 0   # official namespace
        scored.append((org_strong, round(conf, 4), it.get("downloads", 0) or 0, it))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)          # official org first, then name, then popularity
    _os, best_conf, _dl, best = scored[0]
    mid = best.get("id") or best.get("modelId")
    info = _model_info(mid, http)
    license_ = ((info.get("cardData") or {}).get("license")) or _tag_license(info.get("tags"))
    return {"url": f"https://huggingface.co/{mid}", "id": mid,
            "downloads": best.get("downloads", 0), "license": license_,
            "size_gb": _siblings_size_gb(info.get("siblings")), "confidence": round(best_conf, 2)}


_QUANT_KW = ("GGUF", "AWQ", "GPTQ", "FP8")


def find_quants(name, *, http=_get_json, limit=6):
    """Quantized re-uploads of a model (GGUF / AWQ / GPTQ / FP8) so an offline agent can grab a runnable build."""
    out, seen = [], set()
    for kw in _QUANT_KW:
        q = urllib.parse.quote(f"{name} {kw}")
        try:
            res = http(f"{HF_API}/models?search={q}&sort=downloads&direction=-1&limit={limit}", None, 20) or []
        except Exception:
            res = []
        for it in res:
            mid = it.get("id") or it.get("modelId") or ""
            if not mid or mid in seen or kw.lower() not in mid.lower():
                continue
            base = re.sub(kw, "", mid.split("/")[-1], flags=re.I)
            if _name_match(name, base) < 0.5:
                continue
            seen.add(mid)
            out.append({"id": mid, "url": f"https://huggingface.co/{mid}", "fmt": kw,
                        "downloads": it.get("downloads", 0)})
    return out


def find_paper_code(arxiv_id, *, http=_get_json):
    """arXiv id -> the paper's code repo via Papers with Code (official repo preferred)."""
    aid = re.sub(r'v\d+$', '', str(arxiv_id).strip())
    try:
        papers = http(f"{PWC_API}/papers/?arxiv_id={urllib.parse.quote(aid)}", None, 20) or {}
    except Exception:
        return None
    results = papers.get("results") or []
    if not results:
        return None
    slug = results[0].get("id")
    try:
        repos = http(f"{PWC_API}/papers/{slug}/repositories/", None, 20) or {}
    except Exception:
        return None
    rrs = repos.get("results") or []
    if not rrs:
        return None
    rrs.sort(key=lambda r: (not r.get("is_official", False), -(r.get("stars") or 0)))
    top = rrs[0]
    return {"url": top.get("url"), "stars": top.get("stars", 0),
            "official": bool(top.get("is_official")), "confidence": 0.9 if top.get("is_official") else 0.7}


def resolve(name, text="", links=(), *, http=_get_json):
    """Resolve all artifacts for one news item. Links in the post win; missing ones are searched by name.
    Returns a payload-ready dict: github, hf_model, hf_quants, license, size_gb, arxiv."""
    blob = (text or "") + " " + " ".join(links or [])
    out = {"github": None, "hf_model": None, "hf_quants": [], "license": None, "size_gb": 0.0, "arxiv": None}

    gh = _GH_RE.search(blob)
    if gh:
        out["github"] = "https://github.com/" + gh.group(1).rstrip('/')
    hf = _HF_RE.search(blob)
    if hf:
        out["hf_model"] = "https://huggingface.co/" + hf.group(1).rstrip('/')
    ax = _ARXIV_RE.search(blob)
    if ax:
        out["arxiv"] = ax.group(1)

    if not out["github"]:
        fc = find_code(name, http=http)
        if fc:
            out["github"] = fc["url"]
    if not out["hf_model"]:
        owner = None
        if out["github"]:
            m = re.search(r'github\.com/([^/]+)/', out["github"])
            owner = m.group(1) if m else None
        fm = find_model(name, http=http, prefer_org=owner)              # prefer the official HF org (repo owner)
        if fm:
            out["hf_model"] = fm["url"]; out["license"] = fm.get("license"); out["size_gb"] = fm.get("size_gb", 0.0)
    if not out["github"] and out["arxiv"]:
        pc = find_paper_code(out["arxiv"], http=http)
        if pc:
            out["github"] = pc["url"]
    if out["hf_model"]:
        out["hf_quants"] = find_quants(name, http=http)
    return out

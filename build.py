"""Builds the Confluence website into dist/.

    python build.py            build from what the project repos already have
    python build.py --fetch    git fetch each project repo first, so the docs match what is pushed,
                               and read the latest releases from GitHub

Pages:  src/pages/*.html are page bodies with a small header comment (title, description, nav),
        wrapped in src/layout.html. "{{root}}" in a page is the path back to the site root.
Static: src/static/ is copied as it is (style.css, assets/).
Docs:   site.json lists the Markdown guides taken from each project repo. They are read from the
        pushed branch (the "ref", e.g. origin/main) with git, never from the working tree, so only
        published text reaches the site. Links between listed guides stay on the site; other
        repo links go to GitHub; images are copied in.
"""

import argparse
import datetime
import html
import json
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif"}


# ---------------------------------------------------------------- git

def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {repo}: {out.stderr.decode(errors='replace').strip()}")
    return out.stdout if binary else out.stdout.decode("utf-8", errors="replace")


def git_exists(repo, ref, path):
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{ref}:{path}"],
                          capture_output=True).returncode == 0


# ---------------------------------------------------------------- pages

def read_page(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"<!--\n(.*?)\n-->\n", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        text = text[m.end():]
    return meta, text


def nav_html(site, active, root):
    items = []
    for n in site["nav"]:
        href = n["href"] if n["href"].startswith("http") else root + n["href"]
        current = ' aria-current="page"' if n["key"] == active else ""
        items.append(f'      <a href="{href}"{current}>{html.escape(n["label"])}</a>')
    return "\n".join(items)


def render(layout, site, *, title, description, nav, root, content, built):
    out = layout
    for key, value in (("nav", nav_html(site, nav, root)), ("content", content),
                       ("title", html.escape(title)), ("description", html.escape(description, quote=True)),
                       ("built", built)):
        out = out.replace("{{" + key + "}}", value)
    return out.replace("{{root}}", root)


# ---------------------------------------------------------------- releases

CACHE = ROOT / ".cache" / "releases.json"


def fetch_releases(site):
    """Each project's published GitHub releases, from the public API (no sign-in needed)."""
    import urllib.request
    out = {}
    for p in site["projects"]:
        slug = (p.get("releases") or {}).get("slug")
        if not slug:
            continue
        req = urllib.request.Request(f"https://api.github.com/repos/{slug}/releases?per_page=30",
                                     headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "confluence-website-build"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
        out[slug] = [{"tag": d["tag_name"], "prerelease": d["prerelease"], "published": d.get("published_at") or "",
                      "url": d["html_url"],
                      "assets": [{"name": a["name"], "size": a["size"], "url": a["browser_download_url"]}
                                 for a in d.get("assets", [])]}
                     for d in data if not d.get("draft")]
    return out


def load_releases(site, fetch):
    """Fresh from GitHub with --fetch (or when nothing is cached yet), otherwise the cached copy.
    A failed fetch falls back to the cache; with no cache the page still builds, linking to GitHub."""
    cached = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else None
    if fetch or cached is None:
        try:
            fresh = fetch_releases(site)
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(fresh, indent=1), encoding="utf-8")
            print(f"releases: {sum(len(v) for v in fresh.values())} read from GitHub")
            return fresh
        except Exception as e:  # network, rate limit: never fail the build over it
            print(f"releases: GitHub not reached ({e}); using {'the cached copy' if cached else 'links only'}")
    return cached or {}


def human_size(n):
    for unit in ("bytes", "KB", "MB"):
        if n < 1024:
            return f"{n} bytes" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def nice_date(iso):
    try:
        d = datetime.date.fromisoformat(iso[:10])
    except ValueError:
        return ""
    return f"{d.day} {d:%B %Y}"


def release_block(rel, files):
    esc = html.escape
    by_name = {a["name"]: a for a in rel["assets"]}
    rows = []
    for f in files:
        a = next((a for a in rel["assets"] if a["name"].endswith(f["ends"])), None)
        if not a:
            continue
        sha = by_name.get(a["name"] + ".sha256")
        sha_link = f' &middot; <a href="{esc(sha["url"])}">SHA-256</a>' if sha else ""
        rows.append(f'<li><a class="dl" href="{esc(a["url"])}"><strong>{esc(f["label"])}</strong>'
                    f'<span>{esc(a["name"])}</span></a><span class="dl-meta">{human_size(a["size"])}{sha_link}</span></li>')
    if not rel["prerelease"]:
        pill = '<span class="pill ok">Latest</span>'
    elif "beta" in rel["tag"].lower():
        pill = '<span class="pill wip">Beta</span>'
    else:
        pill = '<span class="pill info">Pre-release</span>'
    files_html = f'<ul class="dl-list">{"".join(rows)}</ul>' if rows else \
        f'<p class="muted">Files are on the <a href="{esc(rel["url"])}">release page</a>.</p>'
    return (f'<div class="release"><div class="release-head"><h3>{esc(rel["tag"])}</h3>{pill}'
            f'<span class="muted">{nice_date(rel["published"])}</span>'
            f'<a class="notes" href="{esc(rel["url"])}">Release notes</a></div>{files_html}</div>')


def project_downloads(project, releases):
    """The latest release, plus a newer pre-release or beta when there is one."""
    cfg = project.get("releases") or {}
    all_url = f'{project["github"]}/releases'
    if cfg.get("slug") not in releases:
        return f'<p class="muted">Releases are listed <a href="{all_url}">on GitHub</a>.</p>'
    rels = sorted((r for r in releases[cfg["slug"]] if re.match(r"v\d", r["tag"])),
                  key=lambda r: r["published"], reverse=True)
    if not rels:
        return '<p class="muted">No packaged release yet.</p>'
    stable = next((r for r in rels if not r["prerelease"]), None)
    shown = [stable] if stable else []
    if rels[0] is not stable:
        shown.append(rels[0])
    blocks = "".join(release_block(r, cfg.get("files", [])) for r in shown)
    return f'{blocks}<p class="all-releases"><a href="{all_url}">All releases &rarr;</a></p>'


def fill_downloads(body, site, releases):
    for p in site["projects"]:
        tag = "{{downloads:" + p["key"] + "}}"
        if tag in body:
            body = body.replace(tag, project_downloads(p, releases))
    return body


# ---------------------------------------------------------------- markdown

def gh_slug(value, separator="-"):
    """Heading ids the way GitHub makes them, so #anchors written for GitHub still work."""
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return value.replace(" ", separator)


LIST_RE = re.compile(r"^( *)([-*+]|\d+[.)])( +)")


def fix_github_markdown(text):
    """Python-Markdown is stricter than GitHub about lists. Rewrite GitHub-style lists so they render
    the same: four spaces per nesting level, a blank line before a list that follows a paragraph,
    item text re-indented to the item it belongs to, and code fences inside items turned into
    indented code blocks (Python-Markdown only supports fences at the top level)."""
    lines = text.split("\n")
    out = []
    stack = []          # marker indents of the open list items, outermost first
    kind = "blank"      # what the previous line was: blank, text, list, cont
    level = -1          # nesting level of the previous list line or item text
    multi = []          # per open item: it has had a blank line inside it

    def owner(lead):
        """The deepest open item whose marker sits left of this indent."""
        k = -1
        for i, ind in enumerate(stack):
            if ind < lead:
                k = i
        return k

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        lead = len(line) - len(stripped)
        fence = re.match(r"(`{3,}|~{3,})", stripped)

        if fence:
            mark = fence.group(1)
            body, j = [], i + 1
            while j < len(lines) and not (lines[j].lstrip().startswith(mark) and not lines[j].strip()[len(mark):].strip()):
                body.append(lines[j])
                j += 1
            k = owner(lead) if lead and stack else -1
            if k >= 0 or (stack and kind in ("list", "cont") and lead):
                k = max(k, 0)
                pad = " " * (4 * (k + 1) + 4)
                out.append("")
                out.extend(pad + b[min(lead, len(b) - len(b.lstrip())):] if b.strip() else "" for b in body)
                out.append("")
                stack, multi, kind, level = stack[:k + 1], multi[:k + 1], "cont", k
            else:
                if out and out[-1].strip():
                    out.append("")
                out.append(stripped)
                out.extend(b[min(lead, len(b) - len(b.lstrip())):] for b in body)
                out.append(lines[j].lstrip() if j < len(lines) else mark)
                stack, multi, kind, level = [], [], "text", -1
            i = j + 1
            continue

        m = LIST_RE.match(line)
        if m and not (lead >= 4 and not stack):
            while stack and stack[-1] > lead:
                stack.pop()
            multi = multi[:len(stack)]
            if not stack or stack[-1] < lead:
                stack.append(lead)
            new_level = len(stack) - 1
            multi_block = new_level < len(multi) and multi[new_level]
            multi = multi[:new_level] + [False]
            # A blank line first after a paragraph, under item text, or after an item that holds
            # several blocks (Python-Markdown would otherwise read the marker as more text).
            if kind == "text" or (kind == "cont" and (new_level > level or multi_block)):
                out.append("")
            out.append(" " * (4 * new_level) + stripped)
            kind, level = "list", new_level
        elif not stripped:
            out.append("")
            multi = [True] * len(multi)
            kind = "blank"
        elif lead and stack and owner(lead) >= 0:
            k = owner(lead)
            out.append(" " * (4 * (k + 1)) + stripped)
            stack, multi, kind, level = stack[:k + 1], multi[:k + 1], "cont", k
        elif not lead and kind in ("list", "cont"):
            out.append(line)        # a lazy continuation of the item above
            kind = "cont"
        else:
            out.append(line)
            if not lead:
                stack, multi, level = [], [], -1
            kind = "text"
        i += 1
    return "\n".join(out)


def autolink(html_text):
    """GitHub turns bare URLs into links; do the same outside tags, <a> and <code>/<pre>."""
    parts = re.split(r"(<pre.*?</pre>|<code.*?</code>|<a\b.*?</a>|<[^>]+>)", html_text, flags=re.S)
    url = re.compile(r"(?<![\w/\"'=])(https?://[^\s<>()\"']+[^\s<>()\"'.,;:!?])")
    for i, part in enumerate(parts):
        if part and not part.startswith("<"):
            parts[i] = url.sub(r'<a href="\1">\1</a>', part)
    return "".join(parts)


def md_to_html(text):
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "attr_list", "md_in_html", "toc"],
        extension_configs={"toc": {"slugify": gh_slug, "toc_depth": "2-3", "permalink": False}},
    )
    body = md.convert(fix_github_markdown(text))
    return autolink(body), md.toc_tokens


# ---------------------------------------------------------------- docs

def doc_url(project, doc):
    return f"docs/{project['key']}/{doc['slug']}.html"


def rewrite_links(body, project, doc, doc_map, media_dir, repo):
    """Relative links in a doc: to another listed doc -> its site page; to an image -> copied in;
    anything else in the repo -> GitHub."""
    base = posixpath.dirname(doc["path"])

    def fix(m):
        attr, url = m.group(1), html.unescape(m.group(2))
        if re.match(r"^([a-z][a-z0-9+.-]*:|#|//)", url, re.I) or not url:
            return m.group(0)
        path, _, frag = url.partition("#")
        path = path.split("?")[0]
        if not path:
            return m.group(0)
        target = posixpath.normpath(posixpath.join(base, path)).lstrip("/")
        frag = f"#{frag}" if frag else ""
        if target in doc_map:
            return f'{attr}="{doc_map[target]}.html{frag}"'
        if posixpath.splitext(target)[1].lower() in IMAGE_EXT and git_exists(repo, project["ref"], target):
            dest = media_dir / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(git(repo, "show", f"{project['ref']}:{target}", binary=True))
            return f'{attr}="media/{html.escape(target)}"'
        return f'{attr}="{project["github"]}/blob/{project["branch"]}/{html.escape(target)}{frag}"'

    return re.sub(r'\b(href|src)="([^"]*)"', fix, body)


def toc_html(tokens):
    if not tokens:
        return ""
    items = []
    for t in tokens:
        sub = "".join(f'<li class="sub"><a href="#{c["id"]}">{c["name"]}</a></li>' for c in t.get("children", []))
        items.append(f'<li><a href="#{t["id"]}">{t["name"]}</a></li>{sub}')
    return f'<nav class="doc-toc" aria-label="On this page"><h4>On this page</h4><ul>{"".join(items)}</ul></nav>'


def doc_sidebar(project, current):
    groups = {}
    for d in project["docs"]:
        groups.setdefault(d["group"], []).append(d)
    out = [f'<nav class="doc-nav" aria-label="{html.escape(project["name"])} docs">',
           f'<a class="doc-nav-home" href="../index.html">All documentation</a>',
           f'<h4>{html.escape(project["name"])}</h4>']
    for group, docs in groups.items():
        out.append(f'<h5>{html.escape(group)}</h5><ul>')
        for d in docs:
            cur = ' aria-current="page"' if d is current else ""
            out.append(f'<li><a href="{d["slug"]}.html"{cur}>{html.escape(d["title"])}</a></li>')
        out.append("</ul>")
    out.append("</nav>")
    return "".join(out)


def build_docs(site, layout, built):
    index_sections = []
    for project in site["projects"]:
        repo = (ROOT / project["repo"]).resolve()
        if not repo.exists():
            raise RuntimeError(f"{project['name']}: repo not found at {repo}")
        out_dir = DIST / "docs" / project["key"]
        doc_map = {d["path"]: d["slug"] for d in project["docs"]}
        cards = []
        for doc in project["docs"]:
            text = git(repo, "show", f"{project['ref']}:{doc['path']}")
            commit = git(repo, "log", "-1", "--format=%h %cs", project["ref"], "--", doc["path"]).split()
            body, toc = md_to_html(text)
            body = rewrite_links(body, project, doc, doc_map, out_dir / "media", repo)
            source = f'{project["github"]}/blob/{project["branch"]}/{doc["path"]}'
            note = f'<p class="doc-note">{html.escape(project["note"])}</p>' if project["note"] else ""
            content = f"""<section class="doc-section"><div class="wrap doc-layout">
{doc_sidebar(project, doc)}
<article class="doc">
<div class="doc-meta"><span class="eyebrow">{html.escape(project["name"])}</span>
<span>From <a href="{source}"><code>{html.escape(doc["path"])}</code></a>{f", updated {commit[1]} ({commit[0]})" if commit else ""}</span></div>
{note}
{body}
</article>
{toc_html(toc)}
</div></section>"""
            page = render(layout, site, title=f'{doc["title"]} · {project["name"]}', description=doc["summary"],
                          nav="docs", root="../../", content=content, built=built)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f'{doc["slug"]}.html').write_text(page, encoding="utf-8")
            cards.append(f'<a class="card doc-card" href="{project["key"]}/{doc["slug"]}.html">'
                         f'<span class="doc-group">{html.escape(doc["group"])}</span>'
                         f'<h3>{html.escape(doc["title"])}</h3><p>{html.escape(doc["summary"])}</p></a>')
            print(f"  docs/{project['key']}/{doc['slug']}.html  <- {doc['path']}")
        index_sections.append(
            f'<div class="doc-project" id="{project["key"]}"><h2>{html.escape(project["name"])}</h2>'
            f'<p class="section-intro">Guides from the <a href="{project["github"]}">{html.escape(project["name"])}</a> repository.'
            f'{" " + html.escape(project["note"]) if project["note"] else ""}</p>'
            f'<div class="grid three">{"".join(cards)}</div></div>')

    content = f"""<section class="hero hero-small"><div class="wrap">
<span class="eyebrow">Documentation</span>
<h1>Confluence <span class="grad">docs</span></h1>
<p class="lead">Guides for running, building and using each project, taken from the projects' own repositories and rebuilt with every update.</p>
<div class="buttons">{"".join(f'<a class="btn" href="#{p["key"]}">{html.escape(p["name"])}</a>' for p in site["projects"])}</div>
</div></section>
<section class="alt"><div class="wrap">{"".join(index_sections)}</div></section>"""
    page = render(layout, site, title="Documentation · Confluence",
                  description="Guides for Confluence-OpenSim, Confluence Viewer and Confluence-Voice.",
                  nav="docs", root="../", content=content, built=built)
    (DIST / "docs" / "index.html").write_text(page, encoding="utf-8")
    print("  docs/index.html")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="git fetch each project repo before building")
    args = ap.parse_args()

    site = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    layout = (SRC / "layout.html").read_text(encoding="utf-8")
    built = datetime.date.today().isoformat()

    if args.fetch:
        for p in site["projects"]:
            remote = p["ref"].split("/")[0]
            print(f"fetching {p['name']} ({remote})")
            git((ROOT / p["repo"]).resolve(), "fetch", "--quiet", remote)

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(SRC / "static", DIST)

    releases = load_releases(site, args.fetch)

    print("pages:")
    for path in sorted((SRC / "pages").glob("*.html")):
        meta, body = read_page(path)
        body = fill_downloads(body, site, releases)
        page = render(layout, site, title=meta.get("title", path.stem), description=meta.get("description", ""),
                      nav=meta.get("nav", ""), root="", content=body, built=built)
        (DIST / path.name).write_text(page, encoding="utf-8")
        print(f"  {path.name}")

    print("docs:")
    build_docs(site, layout, built)
    print(f"built into {DIST}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"build failed: {e}")

# Confluence-Website

The website for the Confluence project, live at **https://confluence.ddns.net**:

- [Confluence-OpenSim](https://github.com/Ramius1701/Confluence-OpenSim): the OpenSimulator fork (server, Robust, web portal)
- [Confluence-Viewer](https://github.com/Ramius1701/Confluence-Viewer): the Rust viewer, a modified Aurora Viewer
- [Confluence-Voice](https://github.com/Ramius1701/Confluence-Voice): Windows-native spatial WebRTC voice

A small Python build turns the hand-written pages and the projects' own Markdown guides into a static site.

## Building

Needs Python 3 and the pinned Markdown library, plus the three project repos checked out beside this one
(`..\Confluence-OpenSim`, `..\Confluence-Viewer`, `..\Confluence-Voice`).

```powershell
python -m pip install --user -r requirements.txt
python build.py            # build into dist\
python build.py --fetch    # git fetch the project repos first
```

Open `dist\index.html` to look at the result. `dist\` is never committed.

## Layout

| Path | What it is |
|---|---|
| `src/layout.html` | The page frame: head, header, nav, footer. `{{root}}` is the path back to the site root. |
| `src/pages/*.html` | Page bodies (home, get started, OpenSim, Viewer, Voice), each with a short header comment: title, description, nav. |
| `src/static/` | Copied as it is: `style.css`, `assets/`. |
| `site.json` | The nav, and the guides published from each project repo. |
| `build.py` | The build. |
| `Deploy.ps1` | Builds and publishes to Laragon. |

## Docs from the project repos

`site.json` lists, per project, which Markdown files become pages under `docs/`, with their title, group and summary.
They are read with git from the pushed branch (`ref`, such as `origin/main`), never from the working tree, so
unpushed edits never reach the site. Links between listed guides stay on the site, images are copied in, and every
other repo link goes to GitHub. To publish another guide, add it to `site.json`.

Project logs, agent instructions and internal assessments are left out on purpose.

## Downloads

`src/pages/downloads.html` holds a `{{downloads:<project key>}}` tag per project. The build fills it with that
project's latest release, plus a newer beta or pre-release when there is one, read from the GitHub releases API
(public, no sign-in). Only tags starting `v<digit>` count, so packs such as `ffmpeg-1` stay off. Which files are
listed, and their labels, come from each project's `releases.files` in `site.json` (matched by filename ending); a
`.sha256` file beside one is linked as its checksum.

`--fetch` reads the releases afresh and keeps a copy in `.cache/releases.json`; a plain build uses that copy. If
GitHub can't be reached, the cached copy is used, and with none the page links to the releases on GitHub instead.

## Hosting

Served by Laragon's Apache on the grid machine.

- Publish with `.\Deploy.ps1`: it fetches the project repos, builds, and mirrors `dist\` into
  `S:\laragon\www\confluence`. `-NoFetch` skips the fetch. Editing the repo alone changes nothing live.
  The build runs in `.venv\` (made by the first deploy from `requirements.txt`), not per-user packages.
- The scheduled task "Confluence website deploy" (the owner's account, daily at 06:00, or at the next logon if
  missed) runs `Deploy.ps1`, so what the projects push and release reaches the site within a day. Its output is in
  `.cache\deploy.log`. Hand-written pages (`src/pages`) still change only when edited and pushed here.
- Apache site: `S:\laragon\etc\apache2\sites-enabled\zzz-public-confluence.conf` (HTTP sends to HTTPS, except
  `/.well-known` for certificate renewal).
- Certificate: Let's Encrypt via win-acme, renewal named `confluence`, renewed by the daily "win-acme renew" task and
  put in place by `S:\win-acme\Scripts\Deploy-ApacheCerts.ps1 -Name confluence` (into `S:\laragon\etc\ssl\confluence`).

## Keeping it accurate

The guides update themselves on each deploy. The hand-written pages' figures (test counts, versions, what is
live-verified) come from each project's README, `FEATURES.md` and testing docs; update them when those change.

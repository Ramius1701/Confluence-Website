# Confluence-Website

The website for the Confluence projects:

- [Confluence-OpenSim](https://github.com/Ramius1701/Confluence-OpenSim): the OpenSimulator fork (server, Robust, web portal)
- [Confluence-Viewer](https://github.com/Ramius1701/Confluence-Viewer): the Rust viewer, a modified Aurora Viewer
- [Confluence-Voice](https://github.com/Ramius1701/Confluence-Voice): Windows-native spatial WebRTC voice

Plain static HTML and CSS, no build step. Open `index.html` in a browser to view it locally.

## Pages

| File | Page |
|---|---|
| `index.html` | Overview of the platform and the three projects |
| `opensim.html` | Confluence-OpenSim |
| `viewer.html` | Confluence Viewer |
| `voice.html` | Confluence-Voice |
| `style.css` | Shared styles |
| `assets/` | Logo and viewer screenshots (from the Confluence-Viewer repo) |

The header and footer are repeated in each page; change all four when editing them.

## Hosting

Live at **https://confluence.ddns.net**, served by Laragon's Apache on the grid machine.

- Publish changes with `.\Deploy.ps1`, which mirrors the site's files into `S:\laragon\www\confluence`. Editing the
  repo alone changes nothing live.
- Apache site: `S:\laragon\etc\apache2\sites-enabled\zzz-public-confluence.conf` (HTTP sends to HTTPS, except
  `/.well-known` for certificate renewal).
- Certificate: Let's Encrypt via win-acme, renewal named `confluence`, renewed by the daily "win-acme renew" task and
  put in place by `S:\win-acme\Scripts\Deploy-ApacheCerts.ps1 -Name confluence` (into `S:\laragon\etc\ssl\confluence`).

It's also ready for GitHub Pages or any static host (`.nojekyll` is included).

## Keeping it accurate

Status figures (test counts, versions, what is live-verified) come from each project's README, `FEATURES.md` and
testing docs. Update them here when those change.

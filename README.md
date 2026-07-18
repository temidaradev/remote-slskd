# remote-slskd — Soulseek search & downloader

Search anything via a local `slskd` API, see the highest-quality matches ranked in a table, and pick which one to queue for download.

**Quick start**

- **Run:** `./run.sh "search terms"` (or `python3 auto_download.py "search terms"`)
- Results open in a navigable tree, ranked best-first.

**Navigation keys**

| Key | Action |
|---|---|
| `↑` / `↓` (or `k` / `j`) | move between results |
| `Enter` / `→` | expand a result to show the files inside it |
| `←` | collapse |
| `d` | download the highlighted result |
| `q` / `Esc` | cancel |

Piped / non-interactive runs skip the UI and auto-select the top result.

**With the Nix flake**

- `nix develop` — opens a dev shell that auto-starts `slskd` on port 5030 (web login disabled, API key wired up, `/mnt/1TB-HDD/Synced/Music` shared) and reads Soulseek creds from `.env`.
- `nix run . -- "search terms"` — run the downloader directly.

**Requirements**

- Python 3
- `requests` and `python-dotenv` (installed automatically by `run.sh` if missing)
- Docker + `slskd` (API at `http://localhost:5030`)

**Configuration**

Copy `.env.example` to `.env` and adjust as needed:

- `SLSKD_URL` — slskd API endpoint (default `http://localhost:5030`)
- `MIN_BITRATE` — minimum bitrate (kbps) to accept for files that report one
- `PREFER_FLAC` — only queue lossless `.flac` matches when `true`; also allow lossy formats when `false`

**Notes**

- The script talks to a local `slskd` instance. The API key is set directly in `auto_download.py`.

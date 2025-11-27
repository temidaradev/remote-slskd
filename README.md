# auto-soul — Soulseek album downloader

Short script to search for albums via a local `slskd` API and queue high-quality flac matches for download.

**Quick start**

- **Run:** `./run.sh "Artist - Album"`
- **If you use Docker for `slskd`:** ensure the daemon is running (the runner tries to start Docker auto-magically).

**Requirements**

- Python 3
- `requests` (installed automatically by `run.sh` if missing)
- Docker + `slskd` (API at `http://localhost:5030`)

**Notes**

- The script talks to a local `slskd` instance; set its API URL/API key in the script or environment if different.

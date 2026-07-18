#!/usr/bin/env python3
import os
import sys
import time

try:
    import requests
except ImportError:
    print("✗ The 'requests' library is required.")
    print("  Install it with: pip install requests")
    sys.exit(1)

# Optional: load configuration from a local .env file if python-dotenv is
# installed. The script still works from plain environment variables without it.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# curses powers the interactive tree view. It is part of the stdlib on Linux/
# macOS; if it is unavailable we fall back to a plain numbered prompt.
try:
    import curses
except ImportError:
    curses = None

# --- Configuration -----------------------------------------------------------
# SLSKD_URL, MIN_BITRATE, PREFER_FLAC and MIN_FILES are read from the
# environment / .env. The API key is intentionally hardcoded here.
API_URL = os.environ.get("SLSKD_URL", "http://localhost:5030")
API_KEY = "copilot-secret-key-123456789"
MIN_BITRATE = int(os.environ.get("MIN_BITRATE", "320"))
MIN_FILES = int(os.environ.get("MIN_FILES", "1"))
PREFER_FLAC = os.environ.get("PREFER_FLAC", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# How many results to list for selection.
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "20"))

# Search timing. Stop early once we have ENOUGH_RESULTS users (searches keep
# trickling in for a while, but the top matches show up fast).
SEARCH_TIMEOUT = int(os.environ.get("SEARCH_TIMEOUT", "8000"))
MAX_WAIT = int(os.environ.get("MAX_WAIT", "15"))
ENOUGH_RESULTS = int(os.environ.get("ENOUGH_RESULTS", "15"))

# Server-side cap: slskd ends the search once this many responses arrive, so it
# actually stops (important on a low-power host) instead of running the full
# window. Keep it >= ENOUGH_RESULTS so the client has enough to rank.
RESPONSE_LIMIT = int(os.environ.get("RESPONSE_LIMIT", "100"))

LOSSLESS_EXTS = (".flac",)
LOSSY_EXTS = (".mp3", ".m4a", ".ogg", ".opus", ".wav", ".aac")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}


def search(query):
    """Run a search and return the raw per-user responses (or None on error)."""
    print(f"→ Searching: {query}\n")

    search_data = {
        "searchText": query,
        "filterResponses": True,
        "searchTimeout": SEARCH_TIMEOUT,
        "responseLimit": RESPONSE_LIMIT,
    }

    try:
        resp = requests.post(
            f"{API_URL}/api/v0/searches", headers=HEADERS, json=search_data
        )
        resp.raise_for_status()
        search_id = resp.json()["id"]

        print("→ Waiting for results", end="", flush=True)
        responses = []

        for i in range(MAX_WAIT):
            time.sleep(1)
            print(".", end="", flush=True)

            status_resp = requests.get(
                f"{API_URL}/api/v0/searches/{search_id}", headers=HEADERS
            )
            search_status = status_resp.json()

            resp = requests.get(
                f"{API_URL}/api/v0/searches/{search_id}/responses", headers=HEADERS
            )
            responses = resp.json()

            if search_status.get("state") == "Completed":
                break

            # Stop early once we have plenty to choose from.
            if len(responses) >= ENOUGH_RESULTS and i >= 2:
                break

        # Stop the search server-side so it doesn't keep running on the host.
        try:
            requests.put(
                f"{API_URL}/api/v0/searches/{search_id}", headers=HEADERS, timeout=5
            )
        except requests.exceptions.RequestException:
            pass

        print(" ✓\n")
        return responses
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Could not reach slskd at {API_URL}")
        print("  Is the slskd daemon running? Check SLSKD_URL in your .env")
        return None
    except requests.exceptions.RequestException as e:
        print(f"\n✗ slskd request failed: {e}")
        return None


def get_sample_rate(file):
    if "sampleRate" in file:
        return file["sampleRate"]

    if "attributes" in file:
        for attr in file["attributes"]:
            if attr.get("attributeType") == 1:
                return attr.get("value", 44100)

    if "bitRate" in file and file["bitRate"]:
        bitrate = file["bitRate"]
        if bitrate >= 2000:
            return 96000
        elif bitrate >= 1411:
            return 44100

    return 44100


def score_quality(files):
    if not files:
        return 0
    sample_rates = [get_sample_rate(f) for f in files]
    avg_rate = sum(sample_rates) / len(sample_rates)

    bitrates = [f.get("bitRate", 0) for f in files]
    avg_bitrate = sum(bitrates) / len(bitrates) if bitrates else 0

    return avg_rate + (avg_bitrate * 0.01)


def format_label(files):
    exts = sorted(
        {os.path.splitext(f["filename"])[1].lstrip(".").upper() for f in files}
    )
    return "/".join(exts) if exts else "?"


def build_candidates(responses):
    """Group each user's files by folder and rank them by quality, then size."""
    allowed_exts = LOSSLESS_EXTS if PREFER_FLAC else LOSSLESS_EXTS + LOSSY_EXTS

    candidates = []
    for user_resp in responses:
        folders = {}
        for f in user_resp["files"]:
            folder = "\\".join(f["filename"].split("\\")[:-1])
            folders.setdefault(folder, []).append(f)

        for folder, folder_files in folders.items():
            if len(folder_files) < MIN_FILES:
                continue

            audio_files = [
                f
                for f in folder_files
                if f["filename"].lower().endswith(allowed_exts)
                and (not f.get("bitRate") or f["bitRate"] >= MIN_BITRATE)
            ]

            if not audio_files:
                continue

            candidates.append(
                {
                    "username": user_resp["username"],
                    "folder": folder.split("\\")[-1] or folder,
                    "files": audio_files,
                    "quality": score_quality(audio_files),
                    "size": sum(f["size"] for f in audio_files),
                }
            )

    candidates.sort(key=lambda c: (c["quality"], c["size"]), reverse=True)
    return candidates


def display(candidates):
    print(f"→ Top {min(len(candidates), MAX_RESULTS)} results (of {len(candidates)}):\n")
    print(
        f"  {'#':>2}  {'Album / Folder':<38} {'User':<14} "
        f"{'Files':>5}  {'Format':<8} {'Quality':>8}  {'Size':>9}"
    )
    print(
        f"  {'-' * 2}  {'-' * 38} {'-' * 14} "
        f"{'-' * 5}  {'-' * 8} {'-' * 8}  {'-' * 9}"
    )

    for i, c in enumerate(candidates[:MAX_RESULTS], start=1):
        album = (c["folder"] or "?")[:38]
        user = c["username"][:14]
        khz = c["quality"] / 1000
        size_mb = c["size"] / (1024 * 1024)
        print(
            f"  {i:>2}  {album:<38} {user:<14} {len(c['files']):>5}  "
            f"{format_label(c['files']):<8} {khz:>6.1f}kHz  {size_mb:>7.1f}MB"
        )
    print()


def _safe_addstr(win, y, x, text, attr=0):
    """addstr that never raises when it hits the edge of the screen."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    try:
        win.addnstr(y, x, text, max(0, w - x - 1), attr)
    except curses.error:
        pass


def _curses_selector(stdscr, candidates):
    """Navigable tree: ↑/↓ move, Enter/→ expand a result to show its files,
    ← collapse, d download the highlighted result, q cancel."""
    curses.curs_set(0)
    stdscr.keypad(True)

    has_color = curses.has_colors()
    if has_color:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)  # folder row
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)  # cursor bar

    expanded = set()
    cursor = 0
    top = 0

    def build_rows():
        rows = []
        for ci, c in enumerate(candidates):
            rows.append(("folder", ci, None))
            if ci in expanded:
                for fi in range(len(c["files"])):
                    rows.append(("file", ci, fi))
        return rows

    def folder_row(rows, ci):
        for idx, (typ, rci, _) in enumerate(rows):
            if typ == "folder" and rci == ci:
                return idx
        return 0

    enter_keys = (curses.KEY_ENTER, 10, 13, ord(" "))

    while True:
        rows = build_rows()
        cursor = max(0, min(cursor, len(rows) - 1))

        h, w = stdscr.getmaxyx()
        body_top = 3
        body_h = max(1, h - body_top - 1)

        if cursor < top:
            top = cursor
        elif cursor >= top + body_h:
            top = cursor - body_h + 1

        stdscr.erase()
        _safe_addstr(stdscr, 0, 0, f" remote-slskd — {len(candidates)} results", curses.A_BOLD)
        _safe_addstr(
            stdscr,
            1,
            0,
            " ↑/↓ move · Enter/→ show files · ← collapse · d download · q quit",
        )
        _safe_addstr(stdscr, 2, 0, " " + "─" * max(0, w - 2))

        for idx in range(top, min(len(rows), top + body_h)):
            y = body_top + (idx - top)
            typ, ci, fi = rows[idx]
            c = candidates[ci]
            selected = idx == cursor

            if typ == "folder":
                marker = "▾" if ci in expanded else "▸"
                khz = c["quality"] / 1000
                size_mb = c["size"] / (1024 * 1024)
                text = (
                    f" {marker} {c['folder']}   "
                    f"[{c['username']} · {len(c['files'])} files · "
                    f"{format_label(c['files'])} {khz:.1f}kHz · {size_mb:.1f}MB]"
                )
                base = curses.color_pair(1) if has_color else curses.A_BOLD
            else:
                f = c["files"][fi]
                name = f["filename"].split("\\")[-1]
                size_mb = f["size"] / (1024 * 1024)
                text = f"       {name}  ({size_mb:.1f}MB)"
                base = curses.A_DIM

            if selected:
                attr = (curses.color_pair(2) if has_color else curses.A_REVERSE)
                _safe_addstr(stdscr, y, 0, text.ljust(w - 1), attr | curses.A_BOLD)
            else:
                _safe_addstr(stdscr, y, 0, text, base)

        _, ci, _ = rows[cursor]
        _safe_addstr(
            stdscr,
            h - 1,
            0,
            f" download target: {candidates[ci]['folder']}".ljust(w - 1),
            curses.A_REVERSE,
        )

        stdscr.refresh()
        key = stdscr.getch()

        if key in (curses.KEY_UP, ord("k")):
            cursor -= 1
        elif key in (curses.KEY_DOWN, ord("j")):
            cursor += 1
        elif key == curses.KEY_NPAGE:
            cursor += body_h
        elif key == curses.KEY_PPAGE:
            cursor -= body_h
        elif key == curses.KEY_HOME:
            cursor = 0
        elif key == curses.KEY_END:
            cursor = len(rows) - 1
        elif key in enter_keys or key in (curses.KEY_RIGHT, ord("l")):
            typ, ci, _ = rows[cursor]
            if typ == "folder":
                if ci in expanded and key in enter_keys:
                    expanded.discard(ci)
                else:
                    expanded.add(ci)
        elif key in (curses.KEY_LEFT, ord("h")):
            typ, ci, _ = rows[cursor]
            expanded.discard(ci)
            if typ == "file":
                cursor = folder_row(build_rows(), ci)
        elif key in (ord("d"), ord("D")):
            _, ci, _ = rows[cursor]
            return candidates[ci]
        elif key in (ord("q"), ord("Q"), 27):
            return None


def _text_prompt(candidates):
    """Plain numbered fallback when curses is unavailable."""
    shown = min(len(candidates), MAX_RESULTS)
    while True:
        try:
            choice = input(
                f"Select a result [1-{shown}], Enter for #1, q to cancel: "
            ).strip()
        except EOFError:
            return candidates[0]

        if choice.lower() in ("q", "quit"):
            print("→ Cancelled")
            return None
        if choice == "":
            return candidates[0]
        if choice.isdigit() and 1 <= int(choice) <= shown:
            return candidates[int(choice) - 1]

        print(f"  Please enter a number between 1 and {shown}, or q to cancel.")


def prompt_selection(candidates):
    """Ask the user which result to download. Returns a candidate or None."""
    if not sys.stdin.isatty():
        display(candidates)
        print("→ Non-interactive input; selecting the top result (#1)\n")
        return candidates[0]

    if curses is not None:
        try:
            return curses.wrapper(_curses_selector, candidates)
        except Exception:
            pass  # fall back to the plain prompt

    display(candidates)
    return _text_prompt(candidates)


def download(candidate):
    total_mb = candidate["size"] / (1024 * 1024)
    khz = candidate["quality"] / 1000

    print("\n→ Selected:")
    print(f"   User:       {candidate['username']}")
    print(f"   Folder:     {candidate['folder']}")
    print(f"   Files:      {len(candidate['files'])}")
    print(f"   Format:     {format_label(candidate['files'])} {khz:.1f}kHz")
    print(f"   Total size: {total_mb:.1f} MB\n")

    print("→ Starting download...")

    download_data = [
        {"filename": f["filename"], "size": f["size"]} for f in candidate["files"]
    ]

    try:
        resp = requests.post(
            f"{API_URL}/api/v0/transfers/downloads/{candidate['username']}",
            headers=HEADERS,
            json=download_data,
            timeout=30,
        )

        if resp.status_code in (200, 201, 204):
            print(f"✓ Success! {len(candidate['files'])} files added to the queue")
            print("  Track downloads:")
            print(f"   {API_URL}")
            print("   ~/slskd/downloads/\n")
            return True

        print(f"✗ Download failed: HTTP {resp.status_code}")
        print(f"  Response: {resp.text[:200]}")
        return False

    except requests.exceptions.RequestException as e:
        print(f"✗ Error: {e}")
        return False


def search_and_select(query):
    responses = search(query)
    if responses is None:
        return False

    if not responses:
        print("✗ No results found")
        print("  Try a different search term")
        return False

    print(f"→ Got results from {len(responses)} users\n")

    candidates = build_candidates(responses)
    if not candidates:
        print("✗ No matching files found (try adjusting MIN_BITRATE / PREFER_FLAC)")
        return False

    chosen = prompt_selection(candidates)
    if chosen is None:
        return False

    return download(chosen)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python3 auto_download.py "search terms"')
        print("\nExamples:")
        print('  python3 auto_download.py "Daft Punk Discovery"')
        print('  python3 auto_download.py "Aphex Twin Windowlicker"')
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    search_and_select(query)

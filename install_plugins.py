#!/usr/bin/env python3
"""
qBittorrent search-plugin installer.

Tests each plugin's base site for reachability, then copies the reachable
(.py) plugins into qBittorrent's engines directory.

qBittorrent picks up the new plugins on next start (or via
Search > Search plugins... > Check for updates).

Usage:
    python install_plugins.py                 # test + install reachable plugins
    python install_plugins.py --all           # install every plugin, skip the test
    python install_plugins.py --dry-run       # show what would happen, copy nothing
    python install_plugins.py --src DIR       # plugin source dir (default: ./ )
    python install_plugins.py --repo owner/name   # fetch plugins from a GitHub repo
    python install_plugins.py --timeout 20    # per-site timeout in seconds
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# Default GitHub repo used by --repo when no value is given.
DEFAULT_REPO = "u064241/qbittorrent-search-plugins"

# Don't fail on the self-signed / expired certs some torrent sites use.
ssl._create_default_https_context = ssl._create_unverified_context

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Plugins whose sites are dead / unreachable in testing — skipped even with no
# --all. Kept here so --all can still force-install them if you want.
KNOWN_DEAD = {"foxcili", "ilcorsaronero", "subtorrents", "mejor"}


def engines_dir() -> Path:
    """Return qBittorrent's search-engine plugin directory for this OS."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA", "")
        return Path(base) / "qBittorrent" / "nova3" / "engines"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/qBittorrent/nova3/engines"
    # Linux / *nix
    cfg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(cfg) / "qBittorrent" / "nova3" / "engines"


def fetch_repo(repo: str, ref: str, dest: Path) -> Path:
    """Download every top-level plugin .py from a GitHub repo into dest.

    repo: "owner/name" or a full github.com URL. Returns dest.
    Uses the unauthenticated GitHub contents API (60 req/h limit, fine here).
    """
    m = re.search(r"github\.com/([^/]+/[^/]+)", repo)
    slug = (m.group(1) if m else repo).removesuffix(".git").strip("/")
    api = f"https://api.github.com/repos/{slug}/contents/?ref={ref}"
    print(f"Fetching plugin list from {slug} ({ref})...")
    req = urllib.request.Request(api, headers={**UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        entries = json.load(r)
    if not isinstance(entries, list):
        raise RuntimeError(f"GitHub API error: {entries.get('message', entries)}")

    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for e in entries:
        name = e.get("name", "")
        if e.get("type") != "file" or not name.endswith(".py") or name.startswith("__"):
            continue
        dl = e.get("download_url")
        if not dl:
            continue
        with urllib.request.urlopen(urllib.request.Request(dl, headers=UA), timeout=30) as resp:
            (dest / name).write_bytes(resp.read())
        count += 1
    print(f"Downloaded {count} plugin file(s).\n")
    return dest


def plugin_files(src: Path) -> list[Path]:
    """All plugin .py files in src (top level only, skip dunder + grave/)."""
    return sorted(
        p for p in src.glob("*.py")
        if not p.name.startswith("__") and p.name != Path(__file__).name
    )


def base_url(py: Path) -> str | None:
    """Extract the first `url = '...'` class attribute from a plugin file."""
    text = py.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"""^\s*url\s*=\s*["']([^"']+)["']""", text, re.MULTILINE)
    return m.group(1) if m else None


def reachable(url: str, timeout: int) -> tuple[bool, str]:
    """True if the site answers with any HTTP status (incl. 3xx/4xx)."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        # Cloudflare 52x = the edge is up but the origin server is down/dead.
        if 520 <= e.code <= 524:
            return False, f"HTTP {e.code} (origin down)"
        # Any other status -> site is alive, just refused this exact path.
        return True, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - any network failure = unreachable
        return False, type(e).__name__


def test_all(plugins: list[Path], timeout: int) -> dict[Path, tuple[bool, str]]:
    """Probe every plugin's site in parallel."""
    def probe(py: Path) -> tuple[Path, tuple[bool, str]]:
        url = base_url(py)
        if not url:
            return py, (False, "no url field")
        return py, reachable(url, timeout)

    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        return dict(ex.map(probe, plugins))


def main() -> int:
    ap = argparse.ArgumentParser(description="Install qBittorrent search plugins.")
    ap.add_argument("--src", type=Path, default=Path(__file__).resolve().parent,
                    help="directory holding the plugin .py files (default: this script's dir)")
    ap.add_argument("--repo", nargs="?", const=DEFAULT_REPO, metavar="owner/name",
                    help=f"fetch plugins from a GitHub repo instead of --src "
                         f"(default repo: {DEFAULT_REPO})")
    ap.add_argument("--ref", default="main",
                    help="git branch/tag to fetch with --repo (default: main)")
    ap.add_argument("--all", action="store_true",
                    help="install every plugin without testing reachability")
    ap.add_argument("--dry-run", action="store_true",
                    help="report only, copy nothing")
    ap.add_argument("--timeout", type=int, default=15,
                    help="per-site reachability timeout in seconds (default 15)")
    args = ap.parse_args()

    tmp: tempfile.TemporaryDirectory | None = None
    if args.repo:
        tmp = tempfile.TemporaryDirectory(prefix="qbt-plugins-")
        try:
            src = fetch_repo(args.repo, args.ref, Path(tmp.name))
        except Exception as e:  # noqa: BLE001
            print(f"Failed to fetch repo: {e}", file=sys.stderr)
            tmp.cleanup()
            return 2
    else:
        src = args.src.resolve()

    plugins = plugin_files(src)
    if not plugins:
        print(f"No plugin .py files found in {src}", file=sys.stderr)
        return 2

    dest = engines_dir()
    print(f"Source : {src}")
    print(f"Target : {dest}")
    print(f"Found  : {len(plugins)} plugin file(s)\n")

    if args.all:
        chosen = plugins
        skipped: list[tuple[Path, str]] = []
    else:
        results = test_all(plugins, args.timeout)
        chosen, skipped = [], []
        for py in plugins:
            ok, why = results[py]
            if ok and py.stem not in KNOWN_DEAD:
                chosen.append(py)
                print(f"  OK    {py.stem:18} ({why})")
            else:
                reason = "known-dead" if py.stem in KNOWN_DEAD else why
                skipped.append((py, reason))
                print(f"  SKIP  {py.stem:18} ({reason})")
        print()

    if not chosen:
        print("Nothing reachable to install.")
        return 1

    if args.dry_run:
        print(f"[dry-run] would install {len(chosen)} plugin(s) to {dest}")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    installed = 0
    for py in chosen:
        shutil.copy2(py, dest / py.name)
        installed += 1
    print(f"Installed {installed} plugin(s) into {dest}")
    if skipped:
        print(f"Skipped {len(skipped)}: {', '.join(p.stem for p, _ in skipped)}")
    print("\nRestart qBittorrent (or Search > Search plugins... > Check for updates) "
          "to load them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

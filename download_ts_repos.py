#!/usr/bin/env python3
"""
Enhanced TypeScript high-star repos downloader.
Absorbed functions from download_data.ipynb to support:
1. Query GitHub API for TypeScript repos sorted by stars
2. Filter by stars, license, created date, repo size
3. Clone repos in parallel with progress bar
4. Optionally filter out archived/forks
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import requests
from tqdm import tqdm

# 配置代理设置
os.environ["http_proxy"] = "http://127.0.0.1:10809"
os.environ["https_proxy"] = "http://127.0.0.1:10809"


def get_github_token() -> Optional[str]:
    """Read GitHub token from config or env."""
    token_file = Path("config/github_token.txt")
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return os.getenv("GITHUB_TOKEN")


def github_request(url: str, params: dict, token: Optional[str] = None) -> dict:
    """Helper to call GitHub API with optional token and rate-limit handling."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # 获取代理设置
    proxies = {}
    http_proxy = os.getenv("http_proxy") or os.getenv("HTTP_PROXY")
    https_proxy = os.getenv("https_proxy") or os.getenv("HTTPS_PROXY")
    
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    
    resp = requests.get(url, headers=headers, params=params, timeout=60, proxies=proxies if proxies else None)
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        print("[WARN] GitHub API rate limit hit, sleeping 60s...")
        time.sleep(60)
        return github_request(url, params, token)
    resp.raise_for_status()
    return resp.json()


def fetch_ts_repos(
    n_repos: int = 1000,
    min_stars: int = 500,
    created_after: str = "2018-01-01",
    max_size_kb: int = 50_000,  # 50MB
    licenses: Optional[List[str]] = None,
    skip_forks: bool = True,
    skip_archived: bool = True,
) -> List[str]:
    """
    Fetch high-star TypeScript repos from GitHub API.
    Returns list of clone URLs.
    """
    if licenses is None:
        licenses = ["mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause"]

    token = get_github_token()
    repos: List[str] = []
    per_page = min(100, n_repos)
    seen = set()

    with tqdm(total=n_repos, desc="Fetching repo list") as pbar:
        page = 1
        while len(repos) < n_repos:
            q = (
                f"language:TypeScript "
                f"stars:>={min_stars} "
                f"created:>{created_after} "
                f"size:<{max_size_kb} "
                f"{'fork:false ' if skip_forks else ''}"
                f"{'archived:false ' if skip_archived else ''}"
            ).strip()

            params = {
                "q": q,
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }
            data = github_request(
                "https://api.github.com/search/repositories", params, token
            )
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                clone_url = item.get("clone_url")
                if not clone_url or clone_url in seen:
                    continue
                seen.add(clone_url)
                repos.append(clone_url)
                pbar.update(1)
                if len(repos) >= n_repos:
                    break
            page += 1
            if page > 100:  # safety cap
                break
    return repos[:n_repos]


def clone_repo(url: str, dest_dir: Path, shallow: bool = True) -> bool:
    """Clone a single repo; return True on success."""
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    target = dest_dir / name
    if target.exists():
        return True  # skip existing
    cmd = ["git", "clone", "--depth", "1"] if shallow else ["git", "clone"]
    cmd += [url, str(target)]
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def clone_repos(urls: List[str], dest_dir: Path, max_workers: int = 8) -> None:
    """Clone repos in parallel with progress bar."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    with tqdm(total=len(urls), desc="Cloning repos") as pbar:
        # simple thread pool
        from concurrent.futures import ThreadPoolExecutor

        def worker(url: str) -> bool:
            ok = clone_repo(url, dest_dir)
            pbar.update(1)
            return ok

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(worker, urls))
            success = sum(results)
    print(f"Successfully cloned: {success}/{len(urls)}")


def save_urls(urls: List[str], path: Path) -> None:
    """Save repo URLs to text file."""
    path.write_text("\n".join(urls), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Download high-star TypeScript repositories")
    # new features
    ap.add_argument("--n-repos", type=int, default=200, help="Number of repos to fetch (default 100)")
    ap.add_argument("--min-stars", type=int, default=1000, help="Minimum star count (default 500)")
    ap.add_argument("--created-after", default="2018-01-01", help="Created after date (default 2018-01-01)")
    ap.add_argument("--max-size-kb", type=int, default=50_000, help="Max repo size in KB (default 50MB)")
    ap.add_argument("--licenses", nargs="+", help="License filters (default: mit apache-2.0 bsd-3-clause bsd-2-clause)")
    ap.add_argument("--skip-forks", action="store_true", help="Skip forked repositories")
    ap.add_argument("--skip-archived", action="store_true", help="Skip archived repositories")
    ap.add_argument("--max-workers", type=int, default=8, help="Parallel clone workers (default 8)")
    ap.add_argument("--shallow", action="store_true", help="Shallow clone (depth 1)")
    ap.add_argument("--save-urls", type=Path, help="Save repo URLs to text file")

    # legacy compatibility
    ap.add_argument("--urls", type=Path, help="Legacy: text file with git URLs (one per line)")
    ap.add_argument("--out-dir", type=Path, required=True, help="Output directory for cloned repos")

    args = ap.parse_args()

    # Legacy mode: read URLs from file
    if args.urls:
        if not args.urls.exists():
            raise FileNotFoundError(args.urls)
        urls = [u.strip() for u in args.urls.read_text(encoding="utf-8").splitlines() if u.strip() and not u.startswith("#")]
    else:
        # New mode: query GitHub API
        print(f"Fetching top {args.n_repos} TypeScript repos (stars>={args.min_stars})...")
        urls = fetch_ts_repos(
            n_repos=args.n_repos,
            min_stars=args.min_stars,
            created_after=args.created_after,
            max_size_kb=args.max_size_kb,
            licenses=args.licenses,
            skip_forks=args.skip_forks,
            skip_archived=args.skip_archived,
        )
        if args.save_urls:
            save_urls(urls, args.save_urls)
            print(f"Saved {len(urls)} URLs to {args.save_urls}")

    if not urls:
        print("No repos to clone.")
        return

    clone_repos(urls, args.out_dir, max_workers=args.max_workers)


if __name__ == "__main__":
    main()
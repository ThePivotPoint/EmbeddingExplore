#!/usr/bin/env python3
"""
Batch extract callgraphs from a directory of TypeScript repos.
"""

import argparse
import json
import os
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

def find_ts_repos(root_dir: Path) -> list[Path]:
    """Find all directories that look like TypeScript repos."""
    repos = []
    for subdir in root_dir.iterdir():
        if subdir.is_dir() and (subdir / "tsconfig.json").exists():
            repos.append(subdir)
    return repos

def run_extractor(repo_path: Path, extractor_script: Path, output_dir: Path) -> tuple[str, bool]:
    """Run the callgraph extractor on a single repo."""
    repo_name = repo_path.name
    output_file = output_dir / f"{repo_name}.jsonl"
    cmd = [
        "node",
        str(extractor_script),
        "--project",
        str(repo_path),
        "--out",
        str(output_file),
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout
        )
        return repo_name, True
    except subprocess.CalledProcessError as e:
        error_message = f"Error processing {repo_name}:\n{e.stderr}"
        return error_message, False
    except subprocess.TimeoutExpired:
        return f"Timeout processing {repo_name}", False

def main() -> None:
    repo_root = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Batch extract callgraphs from TypeScript repos.")
    ap.add_argument(
        "--repos-dir",
        type=Path,
        required=True,
        help="Directory containing cloned TypeScript repositories.",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Output directory for callgraph .jsonl files.",
    )
    ap.add_argument(
        "--extractor-script",
        type=Path,
        default=repo_root / "tscompiler" / "extract_callgraph.js",
        help="Path to the callgraph extractor script.",
    )
    ap.add_argument(
        "--max-workers",
        type=int,
        default=os.cpu_count(),
        help="Number of parallel workers.",
    )
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    repos = find_ts_repos(args.repos_dir)
    if not repos:
        print(f"No TypeScript repos found in {args.repos_dir}")
        return

    print(f"Found {len(repos)} TypeScript repos. Starting extraction...")

    errors = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(run_extractor, repo, args.extractor_script, args.out_dir): repo
            for repo in repos
        }
        with tqdm(total=len(repos), desc="Extracting callgraphs") as pbar:
            for future in as_completed(futures):
                repo_name, success = future.result()
                if not success:
                    errors.append(repo_name)
                pbar.update(1)

    print("\nExtraction complete.")
    if errors:
        print(f"\nEncountered {len(errors)} errors:")
        for error in errors:
            print(error)

if __name__ == "__main__":
    main()

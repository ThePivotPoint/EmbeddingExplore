#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path
from multiprocessing import Pool
from tqdm import tqdm

def run_extractor(repo_dir: Path):
    """
    Run the callgraph extractor on a single repository.
    """
    repo_name = repo_dir.name
    output_file = repo_dir / "callgraph.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        return f"Skipping {repo_name}, callgraph.jsonl already exists."

    tscompiler_dir = Path(__file__).resolve().parent / "tscompiler"
    extractor_script = tscompiler_dir / "extract_callgraph.js"

    cmd = [
        "node",
        str(extractor_script),
        "--project",
        str(repo_dir),
        "--out",
        str(output_file),
    ]

    print(f"Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        print(f"Successfully processed {repo_name}")
        return f"Successfully processed {repo_name}"
    except subprocess.CalledProcessError as e:
        print(f"Error processing {repo_name}: {e.stderr}")
        return f"Error processing {repo_name}: {e.stderr}"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "repo_dir",
        type=Path,
        help="Directory containing TypeScript repositories.",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count(),
        help="Number of worker processes to use.",
    )
    args = ap.parse_args()

    repos = [d for d in args.repo_dir.iterdir() if d.is_dir()]
    
    with Pool(args.workers) as pool:
        results = list(tqdm(pool.imap(run_extractor, repos), total=len(repos), desc="Extracting callgraphs"))

    for result in results:
        print(result)

if __name__ == "__main__":
    main()

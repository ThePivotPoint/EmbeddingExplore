#!/usr/bin/env python3
"""
Build a function pair dataset from a directory of callgraphs.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from tqdm import tqdm

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "repos_dir",
        type=Path,
        help="Directory containing repositories with callgraph.jsonl files.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for the combined pairs .jsonl file.",
    )
    ap.add_argument(
        "--no-negative",
        action="store_true",
        help="Don't generate negative samples.",
    )
    args = ap.parse_args()

    callgraph_files = list(args.repos_dir.glob("**/callgraph.jsonl"))
    if not callgraph_files:
        print(f"No callgraph.jsonl files found in {args.repos_dir}")
        return

    repo_root = Path(__file__).resolve().parent
    builder_script = repo_root / "build_dataset_tscompiler.py"
    
    # Create a temporary file to store intermediate pair data
    temp_output = args.out.with_suffix(".tmp")

    with open(temp_output, "w", encoding="utf-8") as f_out:
        for callgraph_file in tqdm(callgraph_files, desc="Processing callgraphs"):
            cmd = [
                sys.executable,
                str(builder_script),
                "--callgraph",
                str(callgraph_file),
                "--out",
                "-",  # Write to stdout
            ]
            if args.no_negative:
                cmd.append("--no-negative")
            
            try:
                result = subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                f_out.write(result.stdout)
            except subprocess.CalledProcessError as e:
                print(f"Error processing {callgraph_file.name}: {e.stderr}")

    # Rename the temporary file to the final output file
    temp_output.rename(args.out)

    print(f"\nDataset successfully built at: {args.out}")

if __name__ == "__main__":
    main()

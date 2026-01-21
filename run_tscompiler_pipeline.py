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

def _write_uniform_sample(in_path: Path, out_path: Path, sample_size: int) -> int:
    with open(in_path, "r", encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)

    if total_lines == 0:
        return 0

    if total_lines <= sample_size:
        with open(in_path, "r", encoding="utf-8") as f_in, open(out_path, "w", encoding="utf-8") as f_out:
            for line in f_in:
                f_out.write(line)
        return total_lines

    step = max(1, total_lines // sample_size)
    written = 0
    with open(in_path, "r", encoding="utf-8") as f_in, open(out_path, "w", encoding="utf-8") as f_out:
        for i, line in enumerate(f_in):
            if i % step == 0:
                f_out.write(line)
                written += 1
                if written >= sample_size:
                    break
    return written

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
    sample_size = 500
    if args.out.suffix == ".jsonl":
        sample_out = args.out.with_suffix("")
    else:
        sample_out = args.out
    sample_out = sample_out.with_name(sample_out.name + f"_sample{sample_size}.jsonl")
    sampled = _write_uniform_sample(args.out, sample_out, sample_size)
    print(f"Sample dataset built at: {sample_out} ({sampled} lines)")

if __name__ == "__main__":
    main()

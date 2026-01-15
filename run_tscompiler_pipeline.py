import argparse
import subprocess
import sys
from pathlib import Path


def run(project: str, callgraph_out: str, pairs_out: str, no_negative: bool) -> None:
    repo_root = Path(__file__).resolve().parent
    extractor = repo_root / "tscompiler" / "extract_callgraph.js"
    callgraph = Path(callgraph_out)
    callgraph.parent.mkdir(parents=True, exist_ok=True)

    subprocess.check_call(
        [
            "node",
            str(extractor),
            "--project",
            project,
            "--out",
            str(callgraph),
        ]
    )

    cmd = [
        sys.executable,
        str(repo_root / "build_dataset_tscompiler.py"),
        "--callgraph",
        str(callgraph),
        "--out",
        pairs_out,
    ]
    if no_negative:
        cmd.append("--no-negative")
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="TypeScript repo root")
    ap.add_argument("--callgraph-out", required=True, help="Callgraph jsonl output path")
    ap.add_argument("--pairs-out", required=True, help="Pairs jsonl output path")
    ap.add_argument("--no-negative", action="store_true")
    args = ap.parse_args()
    run(args.project, args.callgraph_out, args.pairs_out, args.no_negative)


if __name__ == "__main__":
    main()


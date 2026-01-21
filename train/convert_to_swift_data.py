import json
import random
import argparse
import hashlib
import re
from collections import Counter
from pathlib import Path
from tqdm import tqdm

DEFAULT_REPOS_DIR = Path("/data/k8s/qzq/EmbeddingExplore/embedding_pipeline/ts_repos")
DEFAULT_INPUT_PATH = Path("/data/k8s/qzq/EmbeddingExplore/embedding_pipeline/dataset.jsonl")
DEFAULT_OUT_DIR = Path("/data/k8s/qzq/EmbeddingExplore/embedding_pipeline")
DEFAULT_SEED = 42
DEFAULT_TRAIN_RATIO = 0.8
DEFAULT_VALID_RATIO = 0.1
DEFAULT_TEST_RATIO = 0.1
DEFAULT_SAMPLE_SIZE = 500
DEFAULT_SIMHASH_DISTANCE = 2
DEFAULT_SIMHASH_BANDS = 4
DEFAULT_SIMHASH_SHINGLE_SIZE = 4

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|==|!=|<=|>=|=>|&&|\|\||[-+*/%]=?|[<>]=?")
_STOPWORDS = {
    "function",
    "return",
    "const",
    "let",
    "var",
    "if",
    "else",
    "for",
    "while",
    "switch",
    "case",
    "break",
    "continue",
    "async",
    "await",
    "export",
    "default",
    "import",
    "from",
    "class",
    "interface",
    "type",
    "public",
    "private",
    "protected",
    "static",
    "new",
    "try",
    "catch",
    "finally",
    "number",
    "string",
    "boolean",
    "any",
    "void",
    "null",
    "undefined",
}

def normalize_code(code: str) -> str:
    lines: list[str] = []
    for line in code.splitlines():
        line = line.strip()
        if not line:
            continue
        lines.append(" ".join(line.split()))
    return "\n".join(lines)

def _exact_fingerprint(code: str) -> bytes:
    return hashlib.blake2b(code.encode("utf-8"), digest_size=16).digest()

def _simhash64(tokens: list[str]) -> int:
    if not tokens:
        return 0
    weights = Counter(tokens)
    v = [0] * 64
    for tok, w in weights.items():
        h = int.from_bytes(hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(64):
            if (h >> i) & 1:
                v[i] += w
            else:
                v[i] -= w
    fp = 0
    for i, val in enumerate(v):
        if val > 0:
            fp |= 1 << i
    return fp

def _simhash_features(tokens: list[str], shingle_size: int) -> list[str]:
    if shingle_size <= 1:
        return tokens
    if len(tokens) < shingle_size:
        return tokens
    return [" ".join(tokens[i:i + shingle_size]) for i in range(len(tokens) - shingle_size + 1)]

class SimhashIndex:
    def __init__(self, *, bands: int, max_distance: int):
        if bands <= 0:
            raise ValueError("bands must be > 0")
        if 64 % bands != 0:
            raise ValueError("bands must divide 64")
        if max_distance < 0:
            raise ValueError("max_distance must be >= 0")
        self._bands = bands
        self._band_bits = 64 // bands
        self._mask = (1 << self._band_bits) - 1
        self._max_distance = max_distance
        self._buckets: dict[tuple[int, int], list[int]] = {}

    def _keys(self, fp: int) -> list[tuple[int, int]]:
        keys: list[tuple[int, int]] = []
        for band in range(self._bands):
            part = (fp >> (band * self._band_bits)) & self._mask
            keys.append((band, part))
        return keys

    def has_near(self, fp: int) -> bool:
        candidates: set[int] = set()
        for k in self._keys(fp):
            for cand in self._buckets.get(k, []):
                candidates.add(cand)
        for cand in candidates:
            if (cand ^ fp).bit_count() <= self._max_distance:
                return True
        return False

    def add(self, fp: int) -> None:
        for k in self._keys(fp):
            self._buckets.setdefault(k, []).append(fp)

def is_high_quality(code, min_chars=10, min_lines=3, max_lines=40):
    """
    A simple heuristic to filter out low-quality code snippets.
    """
    # Check 1: Character length
    if len(code) < min_chars:
        return False

    # Check 2: Line count
    num_lines = code.count('\n') + 1
    if not (min_lines <= num_lines <= max_lines):
        return False

    return True

def create_sample_file(input_file, output_file, sample_size):
    """
    Creates a smaller sample file by uniformly sampling from a larger jsonl file.
    """
    try:
        with open(input_file, "r") as f:
            total_lines = sum(1 for _ in f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}. Skipping sample creation.")
        return

    if total_lines == 0:
        print("Warning: Input file is empty. Skipping sample creation.")
        return

    if total_lines < sample_size:
        print(f"Warning: Total lines ({total_lines}) is less than sample size ({sample_size}). The sample file will contain all lines.")
        sample_size = total_lines

    if sample_size == 0:
        print("Sample size is 0, not creating a sample file.")
        return

    step = total_lines // sample_size
    
    with open(input_file, "r") as f_in, open(output_file, "w") as f_out:
        sampled_lines = 0
        for i, line in enumerate(tqdm(f_in, total=total_lines, desc="Creating sample file")):
            if i % step == 0 and sampled_lines < sample_size:
                f_out.write(line)
                sampled_lines += 1

def list_repo_names(repos_dir: Path) -> list[str]:
    if not repos_dir.exists():
        return []
    repo_names: list[str] = []
    for p in repos_dir.iterdir():
        if p.is_dir() and not p.name.startswith("."):
            repo_names.append(p.name)
    repo_names.sort()
    return repo_names

def split_repos(
    repo_names: list[str],
    seed: int,
    train_ratio: float,
    valid_ratio: float,
    test_ratio: float,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    total_ratio = train_ratio + valid_ratio + test_ratio
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError(f"train_ratio + valid_ratio + test_ratio must be 1.0, got {total_ratio}")

    rng = random.Random(seed)
    shuffled = repo_names[:]
    rng.shuffle(shuffled)

    n = len(shuffled)
    n_train = int(n * train_ratio)
    n_valid = int(n * valid_ratio)
    n_test = n - n_train - n_valid

    train_repos = shuffled[:n_train]
    valid_repos = shuffled[n_train:n_train + n_valid]
    test_repos = shuffled[n_train + n_valid:n_train + n_valid + n_test]

    repo_to_split: dict[str, str] = {}
    for r in train_repos:
        repo_to_split[r] = "train"
    for r in valid_repos:
        repo_to_split[r] = "valid"
    for r in test_repos:
        repo_to_split[r] = "test"

    splits = {"train": train_repos, "valid": valid_repos, "test": test_repos}
    return repo_to_split, splits

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--train-ratio", type=float, default=DEFAULT_TRAIN_RATIO)
    ap.add_argument("--valid-ratio", type=float, default=DEFAULT_VALID_RATIO)
    ap.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO)
    ap.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    ap.add_argument("--simhash_enabled", type=bool, default=True)
    ap.add_argument("--simhash-distance", type=int, default=DEFAULT_SIMHASH_DISTANCE)
    ap.add_argument("--simhash-bands", type=int, default=DEFAULT_SIMHASH_BANDS)
    ap.add_argument("--simhash-shingle-size", type=int, default=DEFAULT_SIMHASH_SHINGLE_SIZE)
    return ap.parse_args()

def main():
    args = parse_args()
    repo_names = list_repo_names(args.repos_dir)
    if not repo_names:
        print(f"Error: No repositories found in {args.repos_dir}. Aborting.")
        return
    repo_to_split, splits = split_repos(
        repo_names,
        seed=args.seed,
        train_ratio=args.train_ratio,
        valid_ratio=args.valid_ratio,
        test_ratio=args.test_ratio,
    )

    input_file = str(args.input)
    output_train = args.out_dir / "swift_training_data_train.jsonl"
    output_valid = args.out_dir / "swift_training_data_valid.jsonl"
    output_test = args.out_dir / "swift_training_data_test.jsonl"

    QueryInstruction = "Given a typescript code snippet, find the realted code snippet."
    QueryPrefix = "Instruct: %s \n Query: "%QueryInstruction
    
    try:
        with open(input_file, "r") as f:
            total_lines = sum(1 for _ in f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}. Aborting.")
        return

    simhash_enabled = args.simhash_enabled
    simhash_indexes = {}
    if simhash_enabled:
        for s in ["train", "valid", "test"]:
            simhash_indexes[s] = SimhashIndex(bands=args.simhash_bands, max_distance=args.simhash_distance)

    seen_exact = {s: set() for s in ["train", "valid", "test"]}
    lines_written = {"train": 0, "valid": 0, "test": 0}
    unknown_repo_lines = 0
    skipped_exact = 0
    skipped_similar = 0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (
        open(input_file, "r", encoding="utf-8") as f_in,
        open(output_train, "w", encoding="utf-8") as f_train,
        open(output_valid, "w", encoding="utf-8") as f_valid,
        open(output_test, "w", encoding="utf-8") as f_test,
    ):
        split_to_f = {"train": f_train, "valid": f_valid, "test": f_test}
        for line in tqdm(f_in, total=total_lines, desc="Converting to Swift format"):
            data = json.loads(line)
            query = data.get("query") or ""
            positive = data.get("positive") or ""

            if not query or not positive:
                continue

            query_norm = normalize_code(query)
            positive_norm = normalize_code(positive)

            if not is_high_quality(query_norm) or not is_high_quality(positive_norm):
                continue

            meta = data.get("meta") or {}
            repo = meta.get("repo") or data.get("repo") or ""
            split = repo_to_split.get(repo)
            if split is None:
                split = "train"
                unknown_repo_lines += 1

            q_exact = _exact_fingerprint(query_norm)
            p_exact = _exact_fingerprint(positive_norm)
            if q_exact in seen_exact[split] or p_exact in seen_exact[split]:
                skipped_exact += 1
                continue

            if simhash_enabled:
                q_tokens = [t.lower() for t in _TOKEN_RE.findall(query_norm) if t.lower() not in _STOPWORDS]
                p_tokens = [t.lower() for t in _TOKEN_RE.findall(positive_norm) if t.lower() not in _STOPWORDS]
                q_fp = _simhash64(_simhash_features(q_tokens, args.simhash_shingle_size))
                p_fp = _simhash64(_simhash_features(p_tokens, args.simhash_shingle_size))
                if simhash_indexes[split].has_near(q_fp) or simhash_indexes[split].has_near(p_fp):
                    skipped_similar += 1
                    continue
                simhash_indexes[split].add(q_fp)
                simhash_indexes[split].add(p_fp)

            seen_exact[split].add(q_exact)
            seen_exact[split].add(p_exact)

            # 转换为Swift格式
            swift_data = {
                "messages": [{"role": "user", "content": QueryPrefix + query}],
                "positive_messages": [[{"role": "user", "content": data["positive"]}]],
                "meta": meta
            }
            split_to_f[split].write(json.dumps(swift_data, ensure_ascii=False) + "\n")
            lines_written[split] += 1

    print(f"\nRepos scanned: {len(repo_names)}")
    print(f"Repo split: train={len(splits['train'])}, valid={len(splits['valid'])}, test={len(splits['test'])} (seed={args.seed})")
    print(f"Lines written: train={lines_written['train']}, valid={lines_written['valid']}, test={lines_written['test']}")
    if skipped_exact:
        print(f"Skipped (exact): {skipped_exact}")
    if skipped_similar:
        print(f"Skipped (similar): {skipped_similar} (simhash_distance={args.simhash_distance}, simhash_bands={args.simhash_bands})")
    if unknown_repo_lines:
        print(f"Warning: {unknown_repo_lines} lines had unknown repo and were assigned to train.")
    
    create_sample_file(output_train, args.out_dir / "swift_training_data_train_sample.jsonl", args.sample_size)

if __name__ == "__main__":
    main()

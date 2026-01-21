import json
import random
from tqdm import tqdm

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

def main():
    input_file = "/data/k8s/qzq/EmbeddingExplore/embedding_pipeline/dataset.jsonl"
    output_file = "/data/k8s/qzq/EmbeddingExplore/embedding_pipeline/swift_training_data.jsonl"
    sample_output_file = "/data/k8s/qzq/EmbeddingExplore/embedding_pipeline/swift_training_data_sample.jsonl"
    sample_size = 500

    QueryInstruction = "Given a typescript code snippet, find the realted code snippet."
    QueryPrefix = "Instruct: %s \n Query: "%QueryInstruction
    
    try:
        with open(input_file, "r") as f:
            total_lines = sum(1 for _ in f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_file}. Aborting.")
        return

    seen_queries = set()
    lines_written = 0
    with open(input_file, "r") as f_in, open(output_file, "w") as f_out:
        for line in tqdm(f_in, total=total_lines, desc="Converting to Swift format"):
            data = json.loads(line)
            query = data.get("query") or ""
            positive = data.get("positive") or ""

            if not query or not positive:
                continue

            # 确保 query 和 positive 都是高质量的
            if not is_high_quality(query) or not is_high_quality(positive):
                continue

            if query in seen_queries or positive in seen_queries:
                continue
            else:
                seen_queries.add(query)
                seen_queries.add(positive)
            meta = data.get("meta") or {}
            # 转换为Swift格式
            swift_data = {
                "messages": [{"role": "user", "content": QueryPrefix + query}],
                "positive_messages": [[{"role": "user", "content": data["positive"]}]],
                "meta": meta
            }
            f_out.write(json.dumps(swift_data, ensure_ascii=False) + "\n")
            lines_written += 1

    print(f"\nSuccessfully created {output_file} with {lines_written} lines.")

    # Create the sample file
    create_sample_file(output_file, sample_output_file, sample_size)
    print(f"Successfully created sample file {sample_output_file}")

if __name__ == "__main__":
    main()


import json
import random
from tqdm import tqdm

def create_sample_file(input_file, output_file, sample_size):
    """
    Creates a smaller sample file by uniformly sampling from a larger jsonl file.
    """
    with open(input_file, "r") as f:
        total_lines = sum(1 for _ in f)

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
    
    # First, count the total number of lines for tqdm without loading the file into memory
    with open(input_file, "r") as f:
        total_lines = sum(1 for _ in f)

    seen_queries = set()
    with open(input_file, "r") as f_in, open(output_file, "w") as f_out:
        for line in tqdm(f_in, total=total_lines, desc="Converting to Swift format"):
            data = json.loads(line)
            query = data["query"]

            if query in seen_queries:
                if random.random() > 0.1:  # 10% chance to write a duplicate
                    continue
            else:
                seen_queries.add(query)

            # 转换为Swift格式
            swift_data = {
                "messages": [{"role": "user", "content": QueryPrefix + query}],
                "positive_messages": [{"role": "user", "content": data["positive"]}],
            }
            f_out.write(json.dumps(swift_data, ensure_ascii=False) + "\n")

    print(f"\nSuccessfully created {output_file}")

    # Create the sample file
    create_sample_file(output_file, sample_output_file, sample_size)
    print(f"Successfully created sample file {sample_output_file}")

if __name__ == "__main__":
    main()


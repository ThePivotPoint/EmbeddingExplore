# 支持vpn
export http_proxy=http://127.0.0.1:10809
export https_proxy=http://127.0.0.1:10809

# TypeScript Repo -> CallGraph -> Function Pair 数据
## 1) 安装依赖
`apt-get update -y && apt-get install -y nodejs`

## 2) 安装 TypeScript Compiler API
`cd embedding_pipeline/tscompiler && npm install`

## 3) 生成调用图（TS Compiler 解析 + 类型检查）
`node embedding_pipeline/tscompiler/extract_callgraph.js --project /path/to/ts_repo --out /tmp/callgraph.jsonl`

## 4) 从调用图构建函数级 pair（可选带 negative）
`python embedding_pipeline/build_dataset_tscompiler.py --callgraph /tmp/callgraph.jsonl --out /tmp/pairs.jsonl`

## 5) 一键跑完整流程
`python embedding_pipeline/run_tscompiler_pipeline.py --project /data/k8s/qzq/EmbeddingExplore/embedding_pipeline/test_data --callgraph-out ./callgraph.jsonl --pairs-out ./pairs.jsonl --no-negative`

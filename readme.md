# 支持vpn
export http_proxy=http://127.0.0.1:10809
export https_proxy=http://127.0.0.1:10809

# git push
ssh -T git@github-qzq
git remote set-url origin git@github-qzq:ThePivotPoint/EmbeddingExplore.gi
# TypeScript Repo -> CallGraph -> Function Pair 数据

## 0) 下载高星 TypeScript 仓库（可选）
使用 `download_ts_repos.py` 批量下载 GitHub 上的高星 TypeScript 仓库：
```bash
# 下载 100 个 star>500 的 TypeScript 仓库
python embedding_pipeline/download_ts_repos.py --n-repos 100 --min-stars 500 --out-dir ./ts_repos --save-urls ./ts_repos.txt

# 自定义筛选条件
python embedding_pipeline/download_ts_repos.py \
  --n-repos 50 \
  --min-stars 1000 \
  --created-after 2020-01-01 \
  --max-size-kb 100000 \
  --licenses mit apache-2.0 \
  --skip-forks \
  --skip-archived \
  --out-dir ./high_quality_ts \
  --save-urls ./high_quality_ts.txt
```

该脚本功能：
- 自动查询 GitHub API 获取 TypeScript 仓库，按 star 数排序
- 支持按 star 数、创建时间、仓库大小、许可证等条件筛选
- 自动过滤 fork 和 archived 仓库
- 并行克隆仓库，支持浅克隆节省空间
- 保存仓库列表供后续使用
- 支持 GitHub API 速率限制自动处理

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

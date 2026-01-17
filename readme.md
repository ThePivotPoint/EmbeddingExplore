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

## 3) 批量抽取调用图
下载完成后，使用 `extract_callgraphs.py` 脚本批量抽取调用图：

```bash
python embedding_pipeline/extract_callgraphs.py ./ts_repos
```

该脚本会自动扫描 `--repos-dir` 目录下的所有 TypeScript 项目，并为每个项目生成一个 `.jsonl` 格式的调用图文件，存放在 `--out-dir` 目录中。

## 4) 合并调用图并生成数据集
最后，使用 `run_tscompiler_pipeline.py` 脚本将所有调用图合并成最终的数据集：

```bash
python embedding_pipeline/run_tscompiler_pipeline.py --callgraphs-dir ./callgraphs --out ./dataset.jsonl
```

该脚本会自动处理 `--callgraphs-dir` 目录下的所有 `.jsonl` 文件，并生成一个名为 `dataset.jsonl` 的合并后的数据集。

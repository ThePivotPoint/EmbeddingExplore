#!/bin/bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate py311_embedding
nproc_per_node=4
CUDA_VISIBLE_DEVICES=0,1,2,3 NPROC_PER_NODE=$nproc_per_node swift sft --config sft.yaml
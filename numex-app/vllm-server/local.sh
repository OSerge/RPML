#!/bin/bash
# vLLM for local development (RTX 3060 12GB)
# Model: Qwen2.5-3B-Instruct (~8 GB VRAM)

vllm serve Qwen/Qwen2.5-3B-Instruct \
    --port 8001 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.85 \
    --max-model-len 8192

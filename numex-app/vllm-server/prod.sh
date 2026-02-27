#!/bin/bash
# vLLM for production (DGX Spark)
# Model: Qwen2.5-72B-Instruct

vllm serve Qwen/Qwen2.5-72B-Instruct \
    --port 8001 \
    --host 0.0.0.0 \
    --tensor-parallel-size 4 \
    --max-model-len 32768

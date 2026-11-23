#!/usr/bin/env bash
# 一键抓取：./run.sh  （加 --verbose 看细节）
cd "$(dirname "$0")" || exit 1
exec python3 agent.py "$@"

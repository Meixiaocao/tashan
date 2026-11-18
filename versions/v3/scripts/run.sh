#!/usr/bin/env bash
# 他山取证：一条命令跑全部探针，产出 evidence-*.json 到指定目录。
# 用法：bash run.sh <目标目录> [输出目录]
# 输出目录默认 <目标目录>/评审/evidence/
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "用法: bash run.sh <目标目录> [输出目录]" >&2
  exit 2
fi
TARGET="$(cd "$TARGET" && pwd)"
OUT="${2:-$TARGET/评审/evidence}"
mkdir -p "$OUT" 2>/dev/null || OUT="$(mktemp -d)"

PY=python
command -v python3 >/dev/null 2>&1 && PY=python3

echo "[1/3] 探针"
"$PY" "$DIR/probe.py" "$TARGET" --json > "$OUT/evidence-probe.json"
echo "[2/3] 扫描"
"$PY" "$DIR/scan.py" "$TARGET" --json > "$OUT/evidence-scan.json"
echo "[3/3] 界面"
"$PY" "$DIR/ui.py" "$TARGET" --json > "$OUT/evidence-ui.json"

echo "证据目录：$OUT"
ls -1 "$OUT"

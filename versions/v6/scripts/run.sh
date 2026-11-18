#!/usr/bin/env bash
# 他山取证：一条命令跑全部探针，产出 evidence-*.json 到指定目录。
# 用法：bash run.sh <目标目录> [输出目录]
# 输出目录默认 <目标目录>/评审/evidence/
# 输出为 UTF-8 JSON；写盘后逐个校验可解析。
set -uo pipefail

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
"$PY" "$DIR/probe.py" "$TARGET" --json > "$OUT/evidence-probe.json" || { echo "探针失败" >&2; rm -f "$OUT/evidence-probe.json"; }
echo "[2/3] 扫描"
"$PY" "$DIR/scan.py" "$TARGET" --json > "$OUT/evidence-scan.json" || { echo "扫描失败" >&2; rm -f "$OUT/evidence-scan.json"; }
echo "[3/3] 界面"
"$PY" "$DIR/ui.py" "$TARGET" --json > "$OUT/evidence-ui.json" || { echo "界面失败" >&2; rm -f "$OUT/evidence-ui.json"; }

ok=0
for f in "$OUT"/*.json; do
  [ -e "$f" ] || continue
  if "$PY" -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" "$f" 2>/dev/null; then
    ok=$((ok+1))
  else
    echo "JSON 不可解析（UTF-8）：$f" >&2
  fi
done

echo "证据目录：$OUT（$ok 份通过 UTF-8 解析）"
ls -1 "$OUT" 2>/dev/null

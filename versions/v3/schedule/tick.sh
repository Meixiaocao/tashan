#!/usr/bin/env bash
# 他山定时取证：读 targets.txt，逐个跑探针，写待评审标记。只读对象，不改对象代码。
# 用法：bash tick.sh [--dry-run]
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
LIST="$DIR/targets.txt"
LOG="$DIR/tick.log"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

ts() { date "+%Y-%m-%d %H:%M"; }
STAMP="$(date +%Y%m%d-%H%M)"

if [ ! -f "$LIST" ]; then
  echo "缺少对象清单：$LIST" >&2
  exit 2
fi

mapfile -t TARGETS < <(grep -v '^\s*#' "$LIST" | grep -v '^\s*$' || true)
if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "对象清单为空：$LIST" >&2
  exit 2
fi

echo "[$(ts)] 他山定时取证：${#TARGETS[@]} 个对象" | tee -a "$LOG"
PENDING=0

for item in "${TARGETS[@]}"; do
  target="${item%$'\r'}"
  if [ "$DRY" -eq 1 ]; then
    echo "would probe: $target"
    continue
  fi
  if [ ! -d "$target" ]; then
    echo "[$(ts)] 跳过（不存在）：$target" | tee -a "$LOG"
    continue
  fi
  outdir="$target/评审/evidence"
  if ! mkdir -p "$outdir" 2>/dev/null; then
    outdir="$(mktemp -d)"
    echo "[$(ts)] 对象不可写，证据落临时目录：$outdir" | tee -a "$LOG"
  fi
  if bash "$ROOT/scripts/run.sh" "$target" "$outdir" >> "$LOG" 2>&1; then
    cat > "$target/评审/PENDING.md" 2>/dev/null <<EOF
# 待评审

- 取证时间：$(ts)
- 证据目录：$outdir
- 建议命令：\`他山 $target <维度代号>\`
- 说明：本文件由定时取证生成，只表示"证据已更新"。评审判断需人或有 agent 在场时执行。
EOF
    echo "[$(ts)] 完成：$target → $outdir" | tee -a "$LOG"
    PENDING=$((PENDING+1))
  else
    echo "[$(ts)] 失败：$target（详见 $LOG）" | tee -a "$LOG"
  fi
done

echo "[$(ts)] 结束；待评审 $PENDING 条（见各对象 评审/PENDING.md）" | tee -a "$LOG"

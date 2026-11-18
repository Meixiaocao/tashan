#!/usr/bin/env python3
"""他山自进化：记分、算适应度、快照、回滚。

变异不构成进化。有记分、有比较、有回滚，才叫自进化。

子命令：
  record    追加一轮评分
  fitness   打印全部轮次、趋势与判定
  snapshot  把当前技能内容快照为某个版本
  rollback  还原到某个快照

适应度：
  F = 0.4×修复率 + 0.3×(1−复发率) − 0.2×新增率 − 0.1×成本超限
  修复率   = fixed / 上轮条数
  复发率   = recur / 本轮条数
  新增率   = min(1.5, new / 上轮条数)；首轮记 0
  成本超限 = max(0, 必读行数 / 320 − 1)

注意：本脚本只度量结构健康。**有效性只能由外部对象验证**——
外部收敛率 = (D1 − D2) / D1，D 为同维度首跑/复跑差距条数。
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "versions")
LEDGER = os.path.join(VDIR, "ledger.jsonl")
COST_BUDGET = 320
SNAP_EXCLUDE = {"评审", "评审-他山", "_archive", "versions", "__pycache__"}


def load():
    if not os.path.exists(LEDGER):
        return []
    rows = []
    with open(LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def save_all(rows):
    os.makedirs(VDIR, exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def score(rec, prev):
    """F = 0.35*修复率 + 0.25*(1-复发率) - 0.25*误报率 - 0.10*新增率 - 0.05*成本超限

    误报率 = (fp + 0.5*partial) / 上轮 found，分母是同对象同维度上一轮的主表条数。
    未提供 fp（未做外部复核）时该项不计入，其余权重重归一，F 带 * 号：
    未测不等于 0 分，也不与含该项的轮次直接比。
    """
    prev_found = prev["found"] if prev else 0
    fixed_rate = (rec["fixed"] / prev_found) if prev_found else 0.0
    recur_rate = (rec["recur"] / rec["found"]) if rec.get("found") else 0.0
    new_rate = min(1.5, rec["new"] / prev_found) if prev_found else 0.0
    cost = max(0.0, rec.get("lines", 0) / COST_BUDGET - 1)

    raw = 0.35 * fixed_rate + 0.25 * (1 - recur_rate) - 0.10 * new_rate - 0.05 * cost
    wsum = 0.75
    parts = {
        "fixed_rate": round(fixed_rate, 3),
        "recur_rate": round(recur_rate, 3),
        "new_rate": round(new_rate, 3),
        "cost_excess": round(cost, 3),
    }

    fp = rec.get("fp")
    measured = fp is not None and prev_found > 0
    if measured:
        fp_rate = (fp + 0.5 * (rec.get("partial") or 0)) / prev_found
        raw -= 0.25 * fp_rate
        wsum = 1.0
        parts["fp_rate"] = round(fp_rate, 3)
    parts["measured_fp"] = measured
    return round(raw / wsum, 4), parts


def norm_dims(value):
    """维度组合规范化：去空、统一大写、排序。'G5,C2' 与 'C2,G5' 视为同一组合。"""
    items = {x.strip().upper() for x in str(value or "").split(",") if x.strip()}
    return ",".join(sorted(items))


def prev_same_object(rows, idx):
    """同对象的上一轮；不同对象的轮次不可比。"""
    obj = rows[idx]["object"]
    dims = norm_dims(rows[idx].get("dims", ""))
    for j in range(idx - 1, -1, -1):
        if rows[j]["object"] == obj and norm_dims(rows[j].get("dims", "")) == dims:
            return rows[j]
    return None


def with_scores(rows):
    out = []
    for i, row in enumerate(rows):
        prev = prev_same_object(rows, i)
        if prev is None:
            out.append({**row, "fitness": None, "baseline": True, "parts": {}})
            continue
        f, parts = score(row, prev)
        out.append({**row, "fitness": f, "baseline": False, "parts": parts})
    return out


def cmd_record(args):
    rows = load()
    prev = None
    for _r in reversed(rows):
        if _r.get("object") == args.object and norm_dims(_r.get("dims", "")) == norm_dims(args.dims):
            prev = _r
            break
    rec = {
        "round": len(rows) + 1,
        "version": args.version or f"v{len(rows) + 1}",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "object": args.object,
        "kind": args.kind,
        "dims": norm_dims(args.dims),
        "found": args.found,
        "new": args.new,
        "carried": args.carried,
        "recur": args.recur,
        "fixed": args.fixed,
        "lines": args.lines,
        "fp": args.fp,
        "partial": args.partial,
    }
    total = rec["new"] + rec["carried"] + rec["recur"]
    if total != rec["found"]:
        print(f"警告：new+carried+recur={total} 与 found={rec['found']} 不一致", file=sys.stderr)
    rows.append(rec)
    save_all(rows)
    if prev is None:
        print(f"已记录 R{rec['round']} {rec['version']}（该对象首评，记基线）")
    else:
        f, parts = score(rec, prev)
        print(f"已记录 R{rec['round']} {rec['version']} F={f} {parts}")
    return 0


def cmd_fitness(args):
    rows = with_scores(load())
    if not rows:
        print("尚无记录。先 record。")
        return 0
    head = f"{'轮':>3} {'版本':<5} {'对象':<14} {'条数':>3} {'新':>2} {'留':>2} {'复':>2} {'修':>2} {'行':>4} {'F':>9}"
    print(head)
    for seq, r in enumerate(rows, 1):
        if r["baseline"]:
            f = "baseline"
        else:
            f = f"{r['fitness']}" + ("" if r["parts"].get("measured_fp") else "*")
        print(f"{seq:>3} {r['version']:<5} {r['object'][:14]:<14} {r['found']:>3} "
              f"{r['new']:>2} {r['carried']:>2} {r['recur']:>2} {r['fixed']:>2} "
              f"{r.get('lines', 0):>4} {f:>9}")

    if any(not r["baseline"] and not r["parts"].get("measured_fp") for r in rows):
        print("\n* 误报项未测（无外部复核）：其余项权重重归一，分数不得与含误报项的轮次直接比。")

    scored = [r for r in rows if not r["baseline"]]
    print("\n## 趋势（同对象 + 同维度才可比；换维度即新基线）")
    streak = 0
    for i in range(1, len(scored)):
        a, b = scored[i - 1], scored[i]
        if a["object"] != b["object"]:
            continue
        delta = round(b["fitness"] - a["fitness"], 4)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        print(f"{a['object'][:10]} R{a['round']}→R{b['round']}  Δ={delta:+.4f} {arrow}")
        streak = streak + 1 if delta < 0 else 0

    print("\n## 判定")
    last = rows[-1]
    if last["baseline"]:
        print(f"当前：第 {len(rows)} 条 {last['object']}（首评，记基线）")
        print("VERDICT: BASELINE —— 首次评审该对象，下一轮才有 Δ。")
        return 0
    best = max(scored, key=lambda r: r["fitness"])
    print(f"当前版本：第 {len(rows)} 条 F={last['fitness']}")
    print(f"可比最高：R{best['round']} F={best['fitness']}")
    if streak >= 2:
        print("VERDICT: STOP —— 连续 2 轮下降，停手等人裁定。")
    elif streak == 1:
        print(f"VERDICT: REGRESS —— 本轮下降，回滚到上一版。")
    else:
        print("VERDICT: KEEP —— 未下降，保留当前版本。")
    print("\n提醒：F 只度量结构健康；有效性须由外部对象收敛率验证。")
    return 0


def _copy_dir(src, dst, exclude=frozenset()):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in exclude or name.endswith(".log") or name == "PENDING.md":
            continue
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            _copy_dir(s, d)
        else:
            shutil.copy2(s, d)


def _copy_tree(src, dst):
    _copy_dir(src, dst, SNAP_EXCLUDE)


def cmd_snapshot(args):
    dst = os.path.join(VDIR, args.tag)
    _copy_tree(ROOT, dst)
    print(f"已快照 → {dst}")
    return 0


def cmd_rollback(args):
    src = os.path.join(VDIR, args.tag)
    if not os.path.isdir(src):
        print(f"快照不存在：{src}", file=sys.stderr)
        return 1
    _copy_dir(src, ROOT)
    print(f"已回滚 ← {src}")
    print("注意：回滚只覆盖同名文件；快照中不存在的新增文件不会被删除，需手动核对。")
    return 0


def main():
    p = argparse.ArgumentParser(description="他山自进化")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="追加一轮评分")
    r.add_argument("--object", default="他山自身")
    r.add_argument("--kind", default="skill")
    r.add_argument("--dims", default="")
    r.add_argument("--version", default="")
    r.add_argument("--found", type=int, required=True)
    r.add_argument("--new", type=int, default=0)
    r.add_argument("--carried", type=int, default=0)
    r.add_argument("--recur", type=int, default=0)
    r.add_argument("--fixed", type=int, default=0)
    r.add_argument("--lines", type=int, default=0)
    r.set_defaults(func=cmd_record)

    f = sub.add_parser("fitness", help="查看适应度与判定")
    f.set_defaults(func=cmd_fitness)

    s = sub.add_parser("snapshot", help="快照当前版本")
    s.add_argument("--tag", required=True)
    s.set_defaults(func=cmd_snapshot)

    b = sub.add_parser("rollback", help="回滚到快照")
    b.add_argument("--tag", required=True)
    b.set_defaults(func=cmd_rollback)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

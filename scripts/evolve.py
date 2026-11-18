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
import hashlib
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
WEIGHTS = {"exec": 0.5, "acc": 0.5}
FORMULA = "f5"   # 公式版本：f1 四项含成本与新增；f2 去成本；f3 只收结果项 + 误报
def w_fingerprint():
    """权重指纹：改了权重却忘了改 FORMULA 时，用它报警。"""
    return hashlib.md5(repr(sorted(WEIGHTS.items())).encode()).hexdigest()[:8]


COST_BUDGET = 320
SNAP_EXCLUDE = {"评审", "评审-他山", "_archive", "versions", "__pycache__", ".git"}


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
    """F = 执行质量 × 0.5 + 判准度 × 0.5（有外部复核时）

    执行质量 = 修复率 × (1-复发率)：不做事为 0，修了又回来也要打折。
    判准度 = 1 - 误报率：需要外部复核数据；缺数据时 F 只等于执行质量，带 * 标记。
    载荷与新增条数不进公式。

    只收结果项：修好了吗、会不会回来、判错了没。
    载荷与新增条数不进公式，只做单列提示——两者都是过程量，
    折算成分数会让「查得更深」反而扣分，也会让「多写几行机制」直接掉分。
    结果导向原则见 versions/CHANGELOG.md v13/v14。

    误报率 = (fp + 0.5*partial) / 上轮 found，分母是同对象同维度上一轮的主表条数。
    未提供 fp（未做外部复核）时该项不计入，其余权重重归一，F 带 * 号：
    未测不等于 0 分，也不与含该项的轮次直接比。
    """
    prev_found = prev["found"] if prev else 0
    fixed_rate = (rec["fixed"] / prev_found) if prev_found else 0.0
    recur_rate = (rec["recur"] / rec["found"]) if rec.get("found") else 0.0
    new_rate = min(1.5, rec["new"] / prev_found) if prev_found else 0.0
    cost = max(0.0, rec.get("lines", 0) / COST_BUDGET - 1)

    # 执行质量：修了且没回来才算数。不做事 → 0，不靠"复发率为零"白拿分。
    # 执行可信度：自报的"修好了"要打折。未填 verified 按 0.5，填 0 按 0（声称修了但一条没验）。
    fixed_n = rec.get("fixed") or 0
    verified = rec.get("verified")
    if verified is None:
        cred = 0.5 if fixed_n > 0 else 1.0
    elif fixed_n == 0:
        cred = 1.0
    else:
        cred = min(1.0, verified / fixed_n)
    exec_q = fixed_rate * (1 - recur_rate) * cred
    parts = {
        "fixed_rate": round(fixed_rate, 3),
        "recur_rate": round(recur_rate, 3),
        "exec_quality": round(exec_q, 3),
        "credibility": round(cred, 3),
        "new_rate": round(new_rate, 3),
        "load_excess": round(cost, 3),
    }

    fp = rec.get("fp")
    measured = fp is not None and prev_found > 0
    if measured:
        fp_rate = (fp + 0.5 * (rec.get("partial") or 0)) / prev_found
        f = WEIGHTS["exec"] * exec_q + WEIGHTS["acc"] * (1 - fp_rate)
        parts["fp_rate"] = round(fp_rate, 3)
        parts["accuracy"] = round(1 - fp_rate, 3)
    else:
        f = exec_q
    parts["measured_fp"] = measured
    return round(f, 4), parts


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
    if rows and not args.force:
        scored = with_scores(rows)
        same = [r for r in scored if r["object"] == args.object and not r.get("archived")]
        if len(same) >= 2 and all(r["fitness"] is not None for r in same[-2:]):
            if same[-1]["fitness"] < same[-2]["fitness"]:
                print("拒绝记录：上一轮已判定下降（STOP/REGRESS）。先修问题或加 --force。", file=sys.stderr)
                return 1

    if rows:
        last = rows[-1]
        if last.get("formula") == args.formula and last.get("wfp") and last["wfp"] != w_fingerprint():
            print("警告：权重已改但 FORMULA 未升级，新记录会与旧记录被判为同口径。"
                  f"（末条 wfp={last['wfp']} 当前={w_fingerprint()}）", file=sys.stderr)
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
        "formula": args.formula,
        "wfp": w_fingerprint(),
        "verified": args.verified,
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
    head = f"{'轮':>3} {'版本':<5} {'对象':<14} {'式':<3} {'条数':>3} {'新':>2} {'留':>2} {'复':>2} {'修':>2} {'行':>4} {'F':>9}"
    print(head)
    archived = [(i, r) for i, r in enumerate(rows, 1) if r.get("archived")]
    live = [(i, r) for i, r in enumerate(rows, 1) if not r.get("archived")]
    for seq, r in live:
        if r["baseline"]:
            f = "baseline"
        else:
            f = f"{r['fitness']}" + ("" if r["parts"].get("measured_fp") else "*")
        print(f"{seq:>3} {r['version']:<5} {r['object'][:14]:<14} {r.get('formula', '?'):<3} {r['found']:>3} "
              f"{r['new']:>2} {r['carried']:>2} {r['recur']:>2} {r['fixed']:>2} "
              f"{r.get('lines', 0):>4}{'!' if (r.get('lines', 0) / COST_BUDGET - 1) > 0 else ' '} {f:>9}")

    if archived:
        print(f"\n## 存档（{len(archived)} 条，公式已退役，仅留存）")
        for seq, r in archived:
            print(f"{seq:>3} {r['version']:<5} {r['object'][:14]:<14} {r.get('formula','?'):<3} "
                  f"{r['found']:>3}  {r.get('lines', 0):>4}")

    if any(not r["baseline"] and not r["parts"].get("measured_fp") for r in rows if not r.get("archived")):
        print("\n* 误报项未测（无外部复核）：其余项权重重归一，分数不得与含误报项的轮次直接比。")

    scored = [r for r in rows if not r["baseline"]]
    print("\n## 趋势（同对象 + 同维度 + 同公式才可比）")
    streak = 0
    for i in range(1, len(scored)):
        a, b = scored[i - 1], scored[i]
        if a["object"] != b["object"] or a.get("formula") != b.get("formula"):
            continue
        delta = round(b["fitness"] - a["fitness"], 4)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        print(f"{a['object'][:10]} R{a['round']}→R{b['round']}  Δ={delta:+.4f} {arrow}")
        streak = streak + 1 if delta < 0 else 0

    print("\n## 判定")
    _ev = os.path.join(VDIR, "events.jsonl")
    if os.path.isfile(_ev):
        _last = None
        for _line in open(_ev, encoding="utf-8"):
            if _line.strip():
                _last = _line
        if _last:
            try:
                _e = json.loads(_last)
                print(f"上次回滚：{_e.get('tag')}（{_e.get('ts')}）")
            except ValueError:
                pass

    _tail = [r for r in rows if not r.get("archived")][-3:]
    if len(_tail) == 3 and all(not r["parts"].get("measured_fp") for r in _tail):
        print("提醒：最近 3 轮均无外部复核，F 只含自评部分；下一轮前先向对象方索取复核。")
    last = rows[-1]
    if last["baseline"]:
        print(f"当前：第 {len(rows)} 条 {last['object']}（首评，记基线）")
        print("VERDICT: BASELINE —— 首次评审该对象，下一轮才有 Δ。")
        return 0
    recent = [r for r in scored if r["object"] == last["object"]][-3:]
    if recent:
        avg = round(sum(r["fitness"] for r in recent) / len(recent), 4)
        print(f"近 {len(recent)} 轮均值：{avg}（单轮差值受一拍延迟影响，以均值看趋势）")
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
    ev = os.path.join(VDIR, "events.jsonl")
    with open(ev, "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
                             "event": "rollback", "tag": args.tag}, ensure_ascii=False) + "\n")
    print(f"事件已记 → {ev}")
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
    r.add_argument("--verified", type=int, default=None, help="本轮用命令实际复核过的条数；未填按 0.5 折")
    r.add_argument("--force", action="store_true", help="已判定 STOP 仍继续记录")
    r.add_argument("--formula", default=FORMULA, help="公式版本，不同的分数不可比")
    r.add_argument("--fp", type=int, default=None, help="外部复核判定为误报的条数；不给则误报项记未测")
    r.add_argument("--partial", type=int, default=0, help="半误报条数，按 0.5 计")
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

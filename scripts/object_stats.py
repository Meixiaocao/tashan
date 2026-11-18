# -*- coding: utf-8 -*-
"""外部评审汇总：收敛率与精确率分开报。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(os.path.dirname(HERE), "objects", "ledger.jsonl")


def main():
    if not os.path.isfile(P):
        print("无台账：%s" % P, file=sys.stderr)
        return 1
    rows = [json.loads(l) for l in open(P, encoding="utf-8") if l.strip()]
    if not rows:
        print("台账为空")
        return 0

    print("%-12s %-14s %5s %5s %5s %5s" % ("对象", "批次", "D1", "有效", "收敛", "误报"))
    for i, r in enumerate(rows, 1):
        valid = r.get("d2_valid")
        conv = r.get("converged")
        print("%-12s %-14s %5d %5s %5s %5d" % (
            r["object"], "%s-%d" % (r["date"], i), r["d1"],
            "-" if valid is None else valid, "-" if conv is None else conv,
            r["fp"] + r.get("partial", 0)))

    done = [r for r in rows if r.get("d2_valid") is not None]
    d1 = sum(r["d1"] for r in rows)
    valid = sum(r["d2_valid"] for r in done)
    conv = sum(r["converged"] for r in done)
    fp = sum(r["fp"] + 0.5 * r.get("partial", 0) for r in done)

    print("")
    skipped = len(rows) - len(done)
    if valid:
        print("总收敛率：%d/%d = %.1f%%（仅已复评批次）" % (conv, valid, 100.0 * conv / valid))
    if done:
        d1_done = sum(r["d1"] for r in done)
        print("总精确率：%.1f%%（误报权重 %g/%d，仅已复评批次）" % (100.0 * (1 - fp / d1_done), fp, d1_done))
    if skipped:
        print("另有 %d 个批次待复评，未计入分母（%s）" % (skipped, ", ".join(r["object"] for r in rows if r.get("d2_valid") is None)))
    print("说明：两个数分开看。收敛率低于 30% 且精确率高于 90%，是推不动的稳；反之是有效但噪声多。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

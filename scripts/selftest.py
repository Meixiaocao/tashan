# -*- coding: utf-8 -*-
"""脚本自测：把过去靠人工撞见的盲区固化成断言。

跑法：python scripts/selftest.py
退出码 0 = 全过。
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def load(name):
    p = os.path.join(HERE, name + ".py")
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check(label, got, want):
    ok = got == want
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else "  得到 %r，期望 %r" % (got, want)))
    if not ok:
        FAILS.append(label)


def main():
    ev = load("evolve")
    vf = load("verify")

    print("evolve.score —— 不做事时必须为 0")
    rec = {"fixed": 0, "recur": 0, "found": 3, "new": 3, "lines": 600}
    f, _ = ev.score(rec, {"found": 3})
    check("修复率 0 → F=0", f, 0.0)

    print("evolve.score —— 全修完且复验过为满分")
    rec = {"fixed": 3, "verified": 3, "recur": 0, "found": 3, "new": 0, "lines": 600}
    f, parts = ev.score(rec, {"found": 3})
    check("3/3 复验 → F=1.0", f, 1.0)
    check("可信度 1.0", parts["credibility"], 1.0)

    print("evolve.score —— 自报未复验打 0.5 折")
    rec = {"fixed": 3, "recur": 0, "found": 3, "new": 0, "lines": 600}
    f, parts = ev.score(rec, {"found": 3})
    check("未填 verified → F=0.5", f, 0.5)

    print("evolve.score —— 声称修了但复验 0 条")
    rec = {"fixed": 3, "verified": 0, "recur": 0, "found": 3, "new": 0, "lines": 600}
    f, _ = ev.score(rec, {"found": 3})
    check("verified=0 → F=0.0", f, 0.0)

    print("evolve.score —— 复发要打折")
    rec = {"fixed": 4, "verified": 4, "recur": 2, "found": 4, "new": 0, "lines": 600}
    f, _ = ev.score(rec, {"found": 4})
    check("4/4 修但复发 2 → F=0.5", f, 0.5)

    print("evolve.score —— 修复率不得超过 1（修旧账不冲满分）")
    f, _ = ev.score({"fixed": 4, "verified": 4, "recur": 0, "found": 4, "new": 0, "lines": 600},
                    {"found": 2})
    check("修 4 条、上轮 only 2 → F=1.0 不是 2.0", f, 1.0)

    print("evolve.norm_dims —— 顺序无关")
    check("C2,G5 = G5,C2", ev.norm_dims("G5,C2"), ev.norm_dims("C2,G5"))

    print("evolve.w_fingerprint —— 改权重必变")
    fp0 = ev.w_fingerprint()
    ev.WEIGHTS["exec"] = 0.99
    fp1 = ev.w_fingerprint()
    check("改 WEIGHTS 指纹变化", fp0 != fp1, True)
    ev.WEIGHTS["exec"] = 0.5

    print("verify.FONTSIZE_RE —— 三种写法都要认")
    for text, want in [
        ("font-size: 12px", 12.0),
        ("--fs-md: 14px", 14.0),
        ("--font-body: 1rem", 1.0),
    ]:
        m = vf.FONTSIZE_RE.search(text)
        check("认 %r" % text, float(m.group(1)) if m else None, want)

    print("verify.HEX_RE —— 三位与六位")
    check("#fff 命中", len(vf.HEX_RE.findall("#fff")), 1)
    check("#1a2b3c 命中", len(vf.HEX_RE.findall("#1a2b3c")), 1)

    print("")
    if FAILS:
        print("失败 %d 项：%s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

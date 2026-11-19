# -*- coding: utf-8 -*-
"""报告自检：把格式与取证类的错变成机器检查。

用法：python scripts/report_check.py <报告.md>
退出码 0 = 无警告。
"""
import re
import sys

ABS_WORDS = ["整个仓库", "仓库里没有一处", "全部端点", "没有任何配置", "每一处", "统统"]
TRACE_WORDS = ["扫过", "覆盖范围", "grep -r", "find ", "已核"]


def check(path):
    text = open(path, encoding="utf-8").read()
    warns = []
    oks = []

    # 1 验后值是否贴了真实输出
    blocks = re.findall(r"```(?:bash|sh)?\n(.*?)```", text, re.S)
    guessy = []
    for b in blocks:
        for line in b.split("\n"):
            s = line.strip()
            if re.match(r"^#?\s*当前\s*\d+", s) or re.match(r"^#\s*\d+\s*$", s):
                guessy.append(s)
            if "未跑" in s:
                oks.append("已诚实标注「未跑」")
    if guessy:
        has_cmd = any("$" in b or "实跑" in b for b in blocks)
        if not has_cmd:
            warns.append("验后值块出现「当前 N」但整份报告没有命令输出——基线可能是推的")

    # 2 绝对句有没有范围声明
    hit = [w for w in ABS_WORDS if w in text]
    if hit and not any(w in text for w in TRACE_WORDS):
        warns.append("出现绝对句（%s）但未见取证范围声明——结论可能大于取证" % "、".join(hit[:2]))
    elif hit:
        oks.append("绝对句有范围声明")

    # 3 动作是否标了状态
    # 只在「动作」章节里查，避免差距表的「改」字被误判
    seg = ""
    m = re.search(r"##\s*\d*\s*动作(.*?)(?=\n##\s|\Z)", text, re.S)
    if m:
        seg = m.group(1)
    action_rows = [l for l in seg.split("\n")
                   if l.strip().startswith("|") and ("加" in l or "删" in l or "改" in l)]
    if action_rows:
        bad = []
        for l in action_rows:
            if "不可预测" in l or "只给差距" in l:
                continue
            if "已模拟" not in l and "可预测" not in l:
                bad.append(l)
        if bad:
            warns.append("%d 行动作未标「已模拟／可预测」——可能越过第三门槛" % len(bad))
        else:
            oks.append("动作均标了状态或已降回差距")

    # 4 必备区块
    for name, key in [("存疑区", "存疑"), ("未查范围", "未查范围"), ("自检", "自检")]:
        if key in text:
            oks.append("%s 存在" % name)
        else:
            warns.append("缺 %s" % name)

    # 5 推测区是否被当结论用
    if "推测，未验证" in text or "合起来像什么" in text:
        tail = text[text.find("推测"):]
        if "仍然成立" in tail or "所以" in tail:
            warns.append("推测区出现「所以／仍然成立」——可能用假设反推结论")
        else:
            oks.append("推测区未反推结论")

    # 6 依据强度是否点明
    if "依据" in text and "强" in text and "推理" in text:
        oks.append("依据强度已分档")

    return warns, oks


def main():
    if len(sys.argv) < 2:
        print("用法：python report_check.py <报告.md>", file=sys.stderr)
        return 2
    warns, oks = check(sys.argv[1])
    for o in oks:
        print("  ok    " + o)
    if warns:
        print("")
        for w in warns:
            print("  WARN  " + w)
        print("\n%d 项警告。改完再交。" % len(warns))
        return 1
    print("\n无警告")
    return 0


if __name__ == "__main__":
    sys.exit(main())

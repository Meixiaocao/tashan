#!/usr/bin/env python3
"""他山扫描：秘密字面量 + 危险模式。只读。

命中项一律标"启发式"，需人确认；本脚本不判断意图，只给位置。

用法：python scan.py <目标目录> [--json]
"""
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".next", "target", ".idea", ".vscode", ".playwright-cli", ".pytest_cache", "versions",
}
SCAN_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".vue", ".go", ".rs",
    ".java", ".kt", ".sql", ".sh", ".yml", ".yaml", ".toml", ".ini", ".json",
    ".cfg", ".conf", ".env", ".md", ".ps1",
}
MAX_BYTES = 2 * 1024 * 1024  # 单文件扫描上限

PATTERNS = [
    # (类别, 名称, 正则, 说明)
    ("secret", "硬编码口令", re.compile(r"""(?i)\b(password|passwd|pwd)\s*[:=]\s*["'][^"'\s]{3,}["']"""), "口令明文写在代码里"),
    ("secret", "API 密钥", re.compile(r"""(?i)\b(api[_-]?key|apikey|access[_-]?key|secret[_-]?key|token)\s*[:=]\s*["'][A-Za-z0-9_\-]{12,}["']"""), "密钥明文写在代码里"),
    ("secret", "私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "私钥内容入仓"),
    ("secret", "连接串含账号口令", re.compile(r"""(?i)(mysql|postgres|postgresql|mongodb|redis|amqp)://[^/\s"']+:[^@\s"']+@"""), "连接串内含账号口令"),
    ("secret", "云厂商密钥", re.compile(r"\b(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,})\b"), "云或平台密钥"),
    ("risk", "裸异常吞错", re.compile(r"except\s*(Exception\s*)?:\s*(pass|\.\.\.)\s*$|catch\s*\([^)]*\)\s*\{\s*\}"), "错误被静默吞掉"),
    ("risk", "命令执行", re.compile(r"\b(eval|exec)\s*\(|subprocess\.[a-z_]+\([^)]*shell\s*=\s*True|os\.system\s*\("), "动态执行或 shell 拼接"),
    ("risk", "SQL 拼接", re.compile(r"""(?i)(select|insert|update|delete)[^;]{0,80}(["']\s*\+\s*|\%s[^,)]*\)|\.format\s*\()"""), "查询语句由拼接构造"),
    ("risk", "HTML 直插", re.compile(r"\.innerHTML\s*=|dangerouslySetInnerHTML|v-html\s*="), "未经转义的内容直接进 DOM"),
    ("risk", "跨域放开", re.compile(r"""(?i)Access-Control-Allow-Origin["']?\s*[:=]\s*["']\*["']|allow_origins\s*=\s*\[\s*["']\*["']"""), "跨域通配"),
    ("risk", "无超时请求", re.compile(r"\b(requests\.(get|post|put|delete)|axios\.(get|post)|fetch)\s*\("), "需人工确认是否设了超时"),
    ("risk", "调试开关", re.compile(r"(?i)\b(debug|DEBUG)\s*[:=]\s*(True|true|1)\b"), "调试模式可能带入生产"),
]


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                              if d not in SKIP_DIRS and not d.startswith("评审")]
        for name in filenames:
            yield os.path.join(dirpath, name)


def main():
    if len(sys.argv) < 2:
        print("用法: python scan.py <目标目录> [--json]", file=sys.stderr)
        return 2
    root = os.path.abspath(sys.argv[1])
    hits = []
    scanned = 0
    skipped = []

    for path in walk(root):
        ext = os.path.splitext(path)[1].lower()
        if ext not in SCAN_EXT:
            continue
        try:
            if os.path.getsize(path) > MAX_BYTES:
                skipped.append(os.path.relpath(path, root))
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError:
            skipped.append(os.path.relpath(path, root))
            continue
        scanned += 1
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        for lineno, line in enumerate(lines, 1):
            if len(line) > 4000:
                continue
            if "re.compile(" in line:
                continue  # 规则定义行不算命中
            for kind, name, pattern, note in PATTERNS:
                if pattern.search(line):
                    hits.append({
                        "kind": kind,
                        "rule": name,
                        "note": note,
                        "path": rel,
                        "line": lineno,
                        "text": line.strip()[:160],
                    })

    summary = {}
    for h in hits:
        summary[h["rule"]] = summary.get(h["rule"], 0) + 1
    secrets = sum(1 for h in hits if h["kind"] == "secret")

    result = {
        "root": root,
        "files_scanned": scanned,
        "files_skipped": skipped,
        "hits": hits,
        "summary": summary,
        "secret_hits": secrets,
        "risk_hits": len(hits) - secrets,
    }

    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"# 扫描 {root}")
        print(f"扫描 {scanned} 个文件；命中 {len(hits)} 条（秘密 {secrets}，风险 {len(hits)-secrets}）")
        print("\n## 分类计数")
        for rule, count in sorted(summary.items(), key=lambda x: -x[1]):
            print(f"- {rule}: {count}")
        print("\n## 明细（前 40 条，其余见 --json）")
        for h in hits[:40]:
            print(f"- [{h['kind']}] {h['rule']}  {h['path']}:{h['line']}  {h['text']}")
        if len(hits) > 40:
            print(f"... 另有 {len(hits)-40} 条")
        if skipped:
            print(f"\n## 跳过（超大或不可读）{len(skipped)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())

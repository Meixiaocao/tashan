#!/usr/bin/env python3
"""他山探针：目录规模、体积分布、类信号识别。只读，不改动被审对象。

用法：python probe.py <目标目录> [--top N] [--json]
输出：JSON（默认）或人类可读摘要（--json 关闭时）
"""
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from collections import Counter, defaultdict

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".next", "target", ".idea", ".vscode", ".playwright-cli", ".pytest_cache", "versions",
    "coverage", ".mypy_cache", "egg-info",
}
TEXT_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".vue", ".go", ".rs",
    ".java", ".kt", ".sql", ".sh", ".bash", ".yml", ".yaml", ".toml", ".ini",
    ".md", ".json", ".cfg", ".conf", ".xml", ".ps1",
}
SIGNAL_FILES = {
    "code": ["package.json", "requirements.txt", "go.mod", "Cargo.toml", "pom.xml",
             "build.gradle", "setup.py", "pyproject.toml", "tsconfig.json",
             "index.html", "main.py", "manage.py", "app.py", "server.py",
             "index.js", "main.js", "main.go", "main.rs", "Makefile"],
    "app": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Procfile",
            "fly.toml", "vercel.json"],
    "skill": ["SKILL.md"],
}


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                              if d not in SKIP_DIRS and not d.startswith("评审")]
        for name in filenames:
            yield os.path.join(dirpath, name)


def count_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return None


def main():
    if len(sys.argv) < 2:
        print("用法: python probe.py <目标目录> [--top N]", file=sys.stderr)
        return 2
    root = os.path.abspath(sys.argv[1])
    top_n = 10
    if "--top" in sys.argv:
        try:
            top_n = int(sys.argv[sys.argv.index("--top") + 1])
        except (IndexError, ValueError):
            pass
    if not os.path.isdir(root):
        print(json.dumps({"error": "not a directory", "root": root}, ensure_ascii=False))
        return 1

    by_ext = defaultdict(lambda: {"files": 0, "bytes": 0})
    entries = []
    signals = defaultdict(list)
    md_lines = Counter()
    md_files = defaultdict(set)
    total_files = 0
    total_bytes = 0

    src_files = 0
    src_exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
                ".html", ".css", ".vue", ".sql", ".sh"}

    for path in walk(root):
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        ext = os.path.splitext(path)[1].lower() or "(none)"
        by_ext[ext]["files"] += 1
        by_ext[ext]["bytes"] += size
        total_files += 1
        total_bytes += size
        entries.append({"path": rel, "bytes": size, "ext": ext})
        if ext == ".md" and size <= 200_000:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        t = line.strip()
                        if len(t) >= 15 and t[0] not in "#|-*>\\`":
                            md_lines[t] += 1
                            md_files[t].add(rel)
            except OSError:
                pass
        if ext in src_exts:
            src_files += 1
        base = os.path.basename(path)
        for kind, names in SIGNAL_FILES.items():
            if base in names:
                signals[kind].append(rel)

    if src_files >= 5 and not signals.get("app"):
        signals["code"].append(f"源码文件 {src_files} 个（无构建配置）")

    dup_lines = {
        k: len(v) for k, v in md_files.items()
        if len(v) >= 3 and "<" not in k and ">" not in k
    }
    if len(dup_lines) >= 3:
        signals["os"].append(f"跨文件重复行 {len(dup_lines)} 条")

    entries.sort(key=lambda e: e["bytes"], reverse=True)
    largest = entries[:top_n]
    for item in largest:
        full = os.path.join(root, item["path"])
        if item["ext"] in TEXT_EXT:
            item["lines"] = count_lines(full)

    ext_summary = sorted(
        ({"ext": k, **v} for k, v in by_ext.items()),
        key=lambda x: x["bytes"], reverse=True,
    )

    result = {
        "root": root,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_kb": round(total_bytes / 1024, 1),
        "by_ext": ext_summary,
        "largest": largest,
        "signals": {k: v for k, v in signals.items() if v},
        "signal_counts": {k: len(v) for k, v in signals.items()},
        "os_dup_lines": {"count": len(dup_lines), "samples": list(dup_lines)[:5]},
    }

    if "--json" not in sys.argv:
        print(f"# {root}")
        print(f"文件 {total_files} 个 / {result['total_kb']} KB")
        print("\n## 类信号")
        for kind in ("code", "app", "skill", "os"):
            got = signals.get(kind, [])
            print(f"- {kind}: {len(got)} 条 {got[:5]}")
        print(f"- 跨文件重复行: {len(dup_lines)} 条（≥3 条且无占位符时计为 os 信号）")
        print("\n## 体积前 %d" % top_n)
        for item in largest:
            lines = f" {item['lines']}行" if item.get("lines") else ""
            print(f"- {item['path']}  {item['bytes']/1024:.1f}KB{lines}")
        print("\n## 扩展名分布")
        for row in ext_summary[:12]:
            print(f"- {row['ext']:<10} {row['files']:>4} 个  {row['bytes']/1024:>8.1f} KB")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

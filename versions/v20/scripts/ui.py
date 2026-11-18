#!/usr/bin/env python3
"""他山界面扫描：CSS 断点/颜色/字号分布 + HTML 可达性启发式。只读。

全部输出都是启发式计数与样例位置，需人确认；脚本不下"不合格"结论。

用法：python ui.py <目标目录> [--json]
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
    ".next", "target", ".idea", ".vscode", ".playwright-cli",
}
CSS_EXT = {".css", ".scss", ".less"}
HTML_EXT = {".html", ".htm", ".vue", ".svelte"}
JSX_EXT = {".jsx", ".tsx"}


def walk(root, exts):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                              if d not in SKIP_DIRS and not d.startswith("评审")]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in exts:
                yield os.path.join(dirpath, name)


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


MEDIA_RE = re.compile(r"@media[^{]*\(([^)]*)\)")
HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})\b")
RGB_RE = re.compile(r"rgba?\([^)]*\)")
FONTSIZE_RE = re.compile(r"font-size\s*:\s*([^;}]+)")
IMPORTANT_RE = re.compile(r"!important")
IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
ALT_RE = re.compile(r"\balt\s*=", re.I)
BUTTON_RE = re.compile(r"<button\b[^>]*>", re.I)
TYPE_RE = re.compile(r"\btype\s*=", re.I)
LABEL_RE = re.compile(r"<label\b", re.I)
INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)
ARIA_RE = re.compile(r"\baria-label\s*=", re.I)
INLINE_STYLE_RE = re.compile(r"\bstyle\s*=\s*[\"']", re.I)
TABINDEX_RE = re.compile(r"\btabindex\s*=", re.I)
FOCUS_RE = re.compile(r":focus(-visible|-within)?\b")


def main():
    if len(sys.argv) < 2:
        print("用法: python ui.py <目标目录> [--json]", file=sys.stderr)
        return 2
    root = os.path.abspath(sys.argv[1])
    out = {
        "root": root,
        "css": {"files": 0, "media_queries": [], "colors": {}, "font_sizes": {},
                "important": 0, "focus_rules": 0, "inline_style_attrs": 0},
        "html": {"files": 0, "img": 0, "img_no_alt": 0, "button": 0, "button_no_type": 0,
                 "input": 0, "input_like_unlabeled": 0, "tabindex": 0, "hash_links": 0,
                 "label": 0, "samples": []},
    }

    colors = {}
    fonts = {}
    medias = {}
    for path in walk(root, CSS_EXT):
        text = read(path)
        if not text:
            continue
        out["css"]["files"] += 1
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        for m in MEDIA_RE.finditer(text):
            key = m.group(1).strip()
            medias[key] = medias.get(key, 0) + 1
        for m in HEX_RE.finditer(text):
            key = m.group(0).lower()
            colors[key] = colors.get(key, 0) + 1
        for m in RGB_RE.finditer(text):
            key = re.sub(r"\s+", "", m.group(0).lower())
            colors[key] = colors.get(key, 0) + 1
        for m in FONTSIZE_RE.finditer(text):
            key = m.group(1).strip()
            fonts[key] = fonts.get(key, 0) + 1
        out["css"]["important"] += len(IMPORTANT_RE.findall(text))
        out["css"]["focus_rules"] += len(FOCUS_RE.findall(text))
        out["css"]["inline_style_attrs"] += len(INLINE_STYLE_RE.findall(text))

    for path in walk(root, HTML_EXT | JSX_EXT):
        text = read(path)
        if not text:
            continue
        out["html"]["files"] += 1
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        imgs = IMG_RE.findall(text)
        out["html"]["img"] += len(imgs)
        no_alt = [i for i in imgs if not ALT_RE.search(i)]
        out["html"]["img_no_alt"] += len(no_alt)
        buttons = BUTTON_RE.findall(text)
        out["html"]["button"] += len(buttons)
        out["html"]["button_no_type"] += len([b for b in buttons if not TYPE_RE.search(b)])
        inputs = INPUT_RE.findall(text)
        out["html"]["input"] += len(inputs)
        unlabeled = [i for i in inputs if not ARIA_RE.search(i)]
        out["html"]["input_like_unlabeled"] += len(unlabeled)
        out["html"]["tabindex"] += len(TABINDEX_RE.findall(text))
        out["html"]["label"] += len(LABEL_RE.findall(text))
        out["html"]["hash_links"] += len(re.findall(r"href\s*=\s*[\"']#[\"']", text))
        out["css"]["inline_style_attrs"] += len(INLINE_STYLE_RE.findall(text))
        if (no_alt or unlabeled) and len(out["html"]["samples"]) < 12:
            out["html"]["samples"].append({
                "path": rel,
                "img_no_alt": len(no_alt),
                "input_no_aria": len(unlabeled),
            })

    out["css"]["media_queries"] = sorted(
        ({"query": k, "count": v} for k, v in medias.items()), key=lambda x: -x["count"])
    out["css"]["colors"] = dict(sorted(colors.items(), key=lambda x: -x[1])[:20])
    out["css"]["color_unique"] = len(colors)
    out["css"]["font_sizes"] = dict(sorted(fonts.items(), key=lambda x: -x[1])[:20])
    out["css"]["font_size_unique"] = len(fonts)
    if "--json" in sys.argv:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        c, h = out["css"], out["html"]
        print(f"# 界面扫描 {root}")
        print(f"CSS {c['files']} 个 / HTML {h['files']} 个")
        print("\n## 断点（去重计数）")
        for row in c["media_queries"][:10]:
            print(f"- {row['query']}  ×{row['count']}")
        print(f"\n## 颜色 {c['color_unique']} 种唯一值；字号 {c['font_size_unique']} 种；!important {c['important']} 处；:focus 规则 {c['focus_rules']} 条")
        print(f"## 行内 style 属性 {c['inline_style_attrs']} 处")
        print("\n## 可达性启发式")
        print(f"- img {h['img']} 个，其中无 alt {h['img_no_alt']} 个")
        print(f"- button {h['button']} 个，其中无 type {h['button_no_type']} 个")
        print(f"- input {h['input']} 个，其中无 aria-label {h['input_like_unlabeled']} 个；<label> {h['label']} 个")
        print(f"- tabindex {h['tabindex']} 处；href=\"#\" {h['hash_links']} 处")
        for s in h["samples"]:
            print(f"  · {s['path']}  img无alt {s['img_no_alt']}  input无aria {s['input_no_aria']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

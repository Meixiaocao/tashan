#!/usr/bin/env python3
"""他山复验：只输出可对比的量化值，用于 D2（修后同维度复跑）与 D1 对照。

不做判断、不给结论。数值口径与取证脚本一致，便于两次直接相减。

用法：python verify.py <目标目录> [--json]
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
    ".next", "target", ".idea", ".vscode", ".playwright-cli", ".pytest_cache",
    "versions",
}
CSS_EXT = {".css", ".scss", ".less"}
HTML_EXT = {".html", ".htm", ".vue", ".svelte"}

FONTSIZE_RE = re.compile(r"font-size\s*:\s*([0-9.]+)(px|rem|em|pt)")
HEX_RE = re.compile(r"#([0-9a-fA-F]{3,8})\b")
RGB_RE = re.compile(r"rgba?\([^)]*\)")
MEDIA_RE = re.compile(r"@media[^{]*\(([^)]*)\)")
BUTTON_RE = re.compile(r"<button\b([^>]*)>", re.I)
TYPE_RE = re.compile(r"\btype\s*=", re.I)
INPUT_RE = re.compile(r"<input\b([^>]*)>", re.I)
ARIA_RE = re.compile(r"\baria-label\s*=", re.I)
NAME_RE = re.compile(r"\baria-label(?:ledby)?\s*=", re.I)
LABEL_RE = re.compile(r"<label\b", re.I)
LABEL_BLOCK_RE = re.compile(r"<label\b[^>]*>.*?</label>", re.I | re.S)
FOR_RE = re.compile(r'<label\b[^>]*\bfor\s*=\s*["\']([^"\']+)["\']', re.I)
ID_RE = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']', re.I)
LOADING_RE = re.compile(r"loading|skeleton|spinner|is-loading", re.I)


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


def main():
    if len(sys.argv) < 2:
        print("用法: python verify.py <目标目录> [--json]", file=sys.stderr)
        return 2
    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        print(f"不是目录：{root}", file=sys.stderr)
        return 1

    fonts = {}
    colors = set()
    medias = set()
    loading_hits = 0

    for path in walk(root, CSS_EXT):
        text = read(path)
        if not text:
            continue
        for m in FONTSIZE_RE.finditer(text):
            val, unit = m.group(1), m.group(2)
            try:
                px = float(val) * {"px": 1, "rem": 16, "em": 16, "pt": 1.3333}[unit]
            except (KeyError, ValueError):
                continue
            fonts[f"{val}{unit}"] = round(px, 1)
        for m in HEX_RE.finditer(text):
            colors.add(m.group(0).lower())
        for m in RGB_RE.finditer(text):
            colors.add(re.sub(r"\s+", "", m.group(0).lower()))
        for m in MEDIA_RE.finditer(text):
            medias.add(m.group(1).strip())
        loading_hits += len(LOADING_RE.findall(text))

    buttons = no_type = inputs = no_label = labels = unnamed = 0
    for path in walk(root, HTML_EXT):
        text = read(path)
        if not text:
            continue
        for m in BUTTON_RE.finditer(text):
            buttons += 1
            if not TYPE_RE.search(m.group(1)):
                no_type += 1
        label_spans = [(m.start(), m.end()) for m in LABEL_BLOCK_RE.finditer(text)]
        for_ids = set(FOR_RE.findall(text))
        for m in INPUT_RE.finditer(text):
            inputs += 1
            attrs = m.group(1)
            if not ARIA_RE.search(attrs):
                no_label += 1
            named = bool(NAME_RE.search(attrs))
            if not named:
                pos = m.start()
                named = any(start <= pos < end for start, end in label_spans)
            if not named:
                mid = ID_RE.search(attrs)
                if mid and mid.group(1) in for_ids:
                    named = True
            if not named:
                unnamed += 1
        labels += len(LABEL_RE.findall(text))
        loading_hits += len(re.findall(r"\bdata-loading\b|is-loading", text))

    px_values = sorted(fonts.values())
    result = {
        "root": root,
        "font_size_unique": len(fonts),
        "font_size_min_px": px_values[0] if px_values else None,
        "font_size_max_px": px_values[-1] if px_values else None,
        "font_sizes": dict(sorted(fonts.items(), key=lambda kv: kv[1])),
        "color_unique": len(colors),
        "media_breakpoints": len(medias),
        "loading_hits": loading_hits,
        "buttons": buttons,
        "buttons_no_type": no_type,
        "inputs": inputs,
        "inputs_no_aria": no_label,
        "inputs_unnamed": unnamed,
        "media_list": sorted(medias),
        "label_elements": labels,
        "inputs_without_any_label": max(0, inputs - labels - no_label),
    }

    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        rows = [
            ("字号种类", result["font_size_unique"]),
            ("最小字号 px", result["font_size_min_px"]),
            ("最大字号 px", result["font_size_max_px"]),
            ("颜色唯一值", result["color_unique"]),
            ("断点数", result["media_breakpoints"]),
            ("断点值", " | ".join(result["media_list"][:8])),
            ("loading 命中", result["loading_hits"]),
            ("button 总数", result["buttons"]),
            ("无 type 的 button", result["buttons_no_type"]),
            ("input 总数", result["inputs"]),
            ("input 无任何名称", result["inputs_unnamed"]),
            ("其中无 aria-label", result["inputs_no_aria"]),
            ("label 元素", result["label_elements"]),
        ]
        print(f"# 复验指标 {root}")
        for name, val in rows:
            print(f"{name:<22} {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

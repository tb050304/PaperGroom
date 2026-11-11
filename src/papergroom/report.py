"""Generate a self-contained HTML review report.

A formatter that is right 95% of the time is a formatter that is wrong on a
real thesis — so the tool has to show its work. The report lists every
paragraph with the role it was given, how confident the labeler was, and the
style that was applied, with anything uncertain called out.

It is deliberately plain HTML with inline CSS: one file, no assets, opens in
any browser, and can be attached to a bug report.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from .models import Document, Paragraph, ParagraphStyle, Role
from .rules.schema import Ruleset

# Broad colour families so the page is readable at a glance: headings blue,
# body neutral, bibliography purple, figures/tables amber, anything uncertain
# red.
_ROLE_GROUP: dict[str, str] = {
    Role.DOCUMENT_TITLE.value: "heading",
    Role.TITLE_L1.value: "heading",
    Role.TITLE_L2.value: "heading",
    Role.TITLE_L3.value: "heading",
    Role.BODY.value: "body",
    Role.ABSTRACT.value: "abstract",
    Role.FIGURE.value: "media",
    Role.FIGURE_CAPTION.value: "media",
    Role.TABLE.value: "media",
    Role.TABLE_TEXT.value: "media",
    Role.TABLE_CAPTION.value: "media",
    Role.REFERENCE.value: "reference",
    Role.LIST_ITEM.value: "body",
    Role.QUOTE.value: "body",
    Role.FORMULA.value: "media",
    Role.COVER_INFO.value: "cover",
    Role.UNKNOWN.value: "unknown",
}

_ALIGNMENT = {
    "left": "左对齐",
    "center": "居中",
    "right": "右对齐",
    "justify": "两端对齐",
}

_CSS = """
:root { color-scheme: light dark; }
body { font: 15px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
       margin: 32px auto; max-width: 1100px; padding: 0 20px; color: #1d1d1f; background: #fff; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: #6b7280; font-size: 13px; margin-bottom: 20px; }
.summary { display: flex; gap: 22px; flex-wrap: wrap; margin: 0 0 18px; padding: 0; list-style: none; }
.summary li { background: #f3f4f6; border-radius: 6px; padding: 8px 14px; font-size: 13px; }
.summary b { font-size: 18px; display: block; }
.legend { margin: 0 0 16px; font-size: 13px; color: #6b7280; }
.legend span { display: inline-block; margin-right: 14px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 7px 9px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
th { position: sticky; top: 0; background: #fafafa; font-weight: 600; }
td.idx { color: #9ca3af; width: 42px; font-variant-numeric: tabular-nums; }
td.text { font-family: "Microsoft YaHei", sans-serif; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; white-space: nowrap; }
.g-heading .badge { background: #dbeafe; color: #1e40af; }
.g-body .badge { background: #e5e7eb; color: #374151; }
.g-abstract .badge { background: #ccfbf1; color: #115e59; }
.g-media .badge { background: #fef3c7; color: #92400e; }
.g-reference .badge { background: #ede9fe; color: #5b21b6; }
.g-cover .badge { background: #f1f5f9; color: #475569; }
.g-unknown .badge { background: #fee2e2; color: #991b1b; }
.g-heading .dot { background: #3b82f6; }
.g-body .dot { background: #9ca3af; }
.g-abstract .dot { background: #14b8a6; }
.g-media .dot { background: #f59e0b; }
.g-reference .dot { background: #8b5cf6; }
.g-cover .dot { background: #94a3b8; }
.g-unknown .dot { background: #ef4444; }
tr.uncertain { background: #fff7ed; }
tr.uncertain td.idx { color: #b45309; font-weight: 600; }
.conf { font-variant-numeric: tabular-nums; white-space: nowrap; }
.conf.low { color: #b45309; font-weight: 600; }
.style { color: #6b7280; }
.note { margin-top: 20px; font-size: 12px; color: #9ca3af; }
"""


def write_report(
    doc: Document,
    ruleset: Ruleset | None,
    path: str | Path,
    *,
    output_name: str | None = None,
    min_confidence: float = 0.6,
) -> Path:
    """Write the report to ``path`` and return it."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_html(doc, ruleset, output_name=output_name, min_confidence=min_confidence),
        encoding="utf-8",
    )
    return out.resolve()


def render_html(
    doc: Document,
    ruleset: Ruleset | None,
    *,
    output_name: str | None = None,
    min_confidence: float = 0.6,
) -> str:
    """Build the report as a single HTML document."""
    paragraphs = [p for p in doc.paragraphs if not p.is_empty]

    uncertain = [p for p in paragraphs if _is_uncertain(p, min_confidence)]
    unknown = [p for p in paragraphs if p.role == Role.UNKNOWN]
    titled = [p for p in paragraphs if p.role != Role.UNKNOWN]

    rows = "\n".join(_row(p, min_confidence) for p in paragraphs)

    source = html.escape(Path(doc.source_path).name)
    rules_name = html.escape(ruleset.name) if ruleset else "—"
    target = html.escape(output_name) if output_name else "—"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PaperGroom 审查报告 — {source}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>PaperGroom 审查报告</h1>
<div class="meta">
  源文件 <b>{source}</b> · 输出 <b>{target}</b> ·
  规则集 <b>{rules_name}</b> · 生成于 {generated}
</div>

<ul class="summary">
  <li><b>{len(paragraphs)}</b>段落</li>
  <li><b>{len(titled)}</b>已确定角色</li>
  <li><b>{len(unknown)}</b>未确定</li>
  <li><b>{len(uncertain)}</b>需要人工确认</li>
</ul>

<div class="legend">
  <span><i class="dot" style="background:#3b82f6"></i>标题</span>
  <span><i class="dot" style="background:#9ca3af"></i>正文 / 列表 / 引用</span>
  <span><i class="dot" style="background:#14b8a6"></i>摘要</span>
  <span><i class="dot" style="background:#f59e0b"></i>图表 / 公式</span>
  <span><i class="dot" style="background:#8b5cf6"></i>参考文献</span>
  <span><i class="dot" style="background:#94a3b8"></i>封面</span>
  <span><i class="dot" style="background:#ef4444"></i>未确定</span>
  <span>橙色行 = 置信度低于 {min_confidence:g} 或未确定，建议人工检查</span>
</div>

<table>
<thead>
<tr><th>#</th><th>角色</th><th>置信度</th><th>文本</th><th>应用的样式</th></tr>
</thead>
<tbody>
{rows}
</tbody>
</table>

<p class="note">
  置信度为 1.00 表示该角色未经模型判断：由文本规则直接判定，
  或来自人工标注文件（--labels）。
  置信度低于 {min_confidence:g} 的段落保持原格式不变。
</p>
</body>
</html>
"""


def _is_uncertain(para: Paragraph, min_confidence: float) -> bool:
    return para.role == Role.UNKNOWN or para.confidence < min_confidence


def _row(para: Paragraph, min_confidence: float) -> str:
    group = _ROLE_GROUP.get(para.role.value, "unknown")
    classes = [f"g-{group}"]
    if _is_uncertain(para, min_confidence):
        classes.append("uncertain")

    # Unknown roles were never styled; everything else shows what was applied.
    applied = _describe(para.resolved_style)
    confidence = f"{para.confidence:.2f}"
    low = " low" if _is_uncertain(para, min_confidence) else ""
    text = html.escape(para.text.strip()) or "<i>（空对象段落）</i>"

    return (
        f'<tr class="{" ".join(classes)}">'
        f'<td class="idx">{para.index}</td>'
        f'<td><span class="badge">{html.escape(para.role.value)}</span></td>'
        f'<td class="conf{low}">{confidence}</td>'
        f'<td class="text">{text}</td>'
        f'<td class="style">{html.escape(applied)}</td>'
        f"</tr>"
    )


def _describe(style: ParagraphStyle | None) -> str:
    if style is None or style.is_empty():
        return "保持原样"

    bits: list[str] = []
    if style.font_name_east_asian:
        bits.append(style.font_name_east_asian)
    if style.font_name:
        bits.append(style.font_name)
    if style.font_size_pt is not None:
        bits.append(f"{style.font_size_pt:g}pt")
    if style.bold:
        bits.append("粗体")
    if style.italic:
        bits.append("斜体")
    if style.color_hex:
        bits.append(f"#{style.color_hex.lstrip('#')}")
    if style.alignment:
        bits.append(_ALIGNMENT.get(style.alignment, style.alignment))
    if style.first_line_indent_chars is not None:
        bits.append(f"首行缩进{style.first_line_indent_chars:g}字符")
    if style.left_indent_pt is not None:
        bits.append(f"左缩进{style.left_indent_pt:g}pt")
    if style.line_spacing is not None:
        bits.append(f"行距{style.line_spacing:g}")
    if style.space_before_pt is not None:
        bits.append(f"段前{style.space_before_pt:g}pt")
    if style.space_after_pt is not None:
        bits.append(f"段后{style.space_after_pt:g}pt")
    return " · ".join(bits) or "保持原样"

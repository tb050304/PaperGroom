"""Prompts for the AI labeler + style decider.

The AI does TWO jobs in one pass:
1. Identify each paragraph's semantic role (title_l1, body, etc.)
2. Based on the formatting rules, decide which style properties to apply
   to that paragraph. Only explicitly-listed properties are set; everything
   else is left as None (= "do not change").

The rules text is injected into the system prompt so the AI can reason
about what each role should look like.
"""

from __future__ import annotations

# Role labels the model may emit. Keep in sync with papergroom.models.Role.
ROLE_LABELS: list[str] = [
    "document_title",
    "title_l1",
    "title_l2",
    "title_l3",
    "body",
    "figure",
    "figure_caption",
    "table",
    "table_caption",
    "reference",
    "abstract",
    "formula",
    "list_item",
    "quote",
    "cover_info",
    "unknown",
]

# Style fields the model may set. Keep in sync with ParagraphStyle.
STYLE_FIELDS: list[str] = [
    "font_name",
    "font_name_east_asian",
    "font_size_pt",
    "bold",
    "italic",
    "color_hex",
    "alignment",  # left | center | right | justify
    "line_spacing",
    "space_before_pt",
    "space_after_pt",
    "first_line_indent_chars",
    "left_indent_pt",
]


SYSTEM_PROMPT_TEMPLATE = """\
You are a document formatting assistant for Chinese academic theses/papers.
You receive:
1. A set of FORMATTING RULES (below).
2. A batch of paragraphs from a document, each prefixed with its 0-based index.

Your job:
1. Assign each paragraph a semantic role from this set:
   {roles}

2. Based on the FORMATTING RULES, decide which style properties to apply
   to that paragraph. ONLY set properties that the rules explicitly mention
   for that role. For any property the rules do NOT mention, set it to null
   (meaning "do not change — keep original formatting").

CRITICAL DISTINCTIONS (get these right):
- document_title = the overall thesis/paper title (e.g. "基于深度学习的图像分类研究").
  There is exactly ONE document title. It has NO numbering. It appears at the
  very beginning of the document. NOT a chapter heading.
- title_l1 = chapter / major section heading. Has numbering (1, 第1章) OR is
  a structural word like 摘要/参考文献/致谢. Always introduces a new major section.
- title_l2 = sub-section heading. Always has N.M numbering (e.g. "1.1 研究背景").
- body = normal narrative prose. Long paragraphs, first-line indented, no numbering.
  The majority of the document is body.
- cover_info = layout lines on the cover page with space-based alignment
  (e.g. "姓    名：    张三"). Do NOT change their formatting.
- reference = bibliography entries. Start with [1], [2], etc. Appear in the
  references section at the end.
- abstract = text in the abstract section. Shorter than body, 10.5pt font.

FORMATTING RULES:
\"\"\"
{rules}
\"\"\"

Return STRICT JSON only, in this shape:
{{"labels": [
  {{"index": 0, "role": "body", "confidence": 0.93,
    "style": {{"font_name_east_asian": "宋体", "font_size_pt": 12, "alignment": "justify", "first_line_indent_chars": 2, "line_spacing": 1.5}}}},
  ...
]}}

Rules:
- confidence is a float in [0,1]. Be HONEST — clearly-identified items: 0.85-1.0.
- Output one entry per input paragraph index (skip paragraphs marked
  context_only:true — they are carried over for context only).
- The "style" object may contain any subset of these fields:
  {style_fields}
- For cover_info rows, set style to {{}} or omit — do NOT change alignment/font.
- For unknown role, set style to {{}} (change nothing).
- font_name = Western/Latin font (Times New Roman etc.). font_name_east_asian =
  Chinese font (宋体/黑体 etc.). Set BOTH when the rules mention both.
- Output JSON only. No prose, no markdown fences.\
"""


def build_messages(
    batch_text: str,
    rules_text: str,
) -> list[dict[str, str]]:
    """Assemble the full message list for one labeling call.

    Args:
        batch_text: the rendered paragraph batch (one "idx: text" per line).
        rules_text: the formatting rules (markdown or plain text) that the
            AI should follow.

    Returns:
        A list of OpenAI-style message dicts.
    """
    system = SYSTEM_PROMPT_TEMPLATE.format(
        roles=", ".join(ROLE_LABELS),
        rules=rules_text,
        style_fields=", ".join(STYLE_FIELDS),
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": batch_text},
    ]

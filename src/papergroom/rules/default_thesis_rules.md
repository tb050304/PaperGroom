# Default Thesis Formatting Rules (Built-in)

> **STATUS: human reference only — nothing reads this file.**
>
> It used to be pasted into the labeler's prompt, which then asked the model
> to interpret it and emit concrete style values. That is gone: the labeler
> now only decides a paragraph's *role*, and styles come from
> [`standard_thesis.yaml`](standard_thesis.yaml) via
> [`resolve.py`](resolve.py). No code path loads this document.
>
> What remains is the *reasoning* — why each role looks the way it does, and
> how to tell the roles apart. The YAML carries the numbers. The two were
> reconciled when the ruleset was completed and now agree; where they ever
> diverge, **the YAML wins**.
>
> One nuance the YAML cannot yet express: a true hanging indent for
> bibliography entries needs a *negative* first-line indent, which the style
> schema has no field for. `ROADMAP.md` Phase 3 covers that, along with
> deleting this file once the YAML carries the reasoning too.

These rules describe the standard formatting for a Chinese academic thesis / paper
(bachelor's, master's, or doctoral level). The AI reads these rules together with
the document content, identifies each paragraph's semantic role, and applies ONLY
the properties listed below. Properties NOT listed for a role are left unchanged
in the original document.

---

## 1. General Principles

1. **Only change what the rules explicitly specify.** If a rule does not mention
   a property (e.g. italic for a level-1 heading), DO NOT change it — leave the
   original formatting exactly as-is.
2. **Chinese / East Asian text** uses the East Asian font slot (`font_name_east_asian`).
   **Latin / English / numeric** text uses the Western font slot (`font_name`).
3. **Font sizes** are in points (pt). 1pt = 1/72 inch.
   See Section 6 for the Chinese "号" (hào) size reference table.
4. **Line spacing**: a number means a multiple of line height (e.g. 1.5 = 1.5× line height).
5. **First line indent** is measured in "characters" (1 char ≈ font size in pt for CJK).
   For a 12pt font, 2 characters ≈ 24pt.
6. **Left indent** is measured in points (pt). Used for hanging indents and block quotes.
7. **Alignment values**: `left`, `center`, `right`, `justify` (两端对齐).
8. **Original objects are protected**: images, formulas (OMML), and field objects
   only get their paragraph-level style changed; never modify their content, size,
   or internal structure.
9. **When in doubt, mark as `unknown`**. It is better to leave a paragraph
   unchanged than to apply the wrong style. Set `confidence` honestly.

---

## 2. Typical Structure of a Chinese Thesis

Understanding the overall structure helps disambiguate roles. A typical Chinese
thesis flows in this order (not all sections appear in every thesis):

```
封面 (Cover Page)
  └─ document_title, cover_info lines
摘要页 (Abstract Page — Chinese)
  └─ 摘要 (abstract_title) → abstract body → 关键词 (keywords lines)
Abstract Page — English
  └─ "Abstract" → abstract body → "Keywords"
目录 (Table of Contents)
图目录 / 表目录 (List of Figures / Tables)
符号说明 (List of Symbols / Nomenclature)
第1章 绪论 (Chapter 1: Introduction)
  └─ title_l1 → title_l2 → title_l3 → body → figures → tables → formulas
第2章 ... (Chapter 2)
  ... (more chapters)
第N章 总结与展望 (Chapter N: Conclusion)
参考文献 (References)
  └─ reference_title → reference entries
致谢 (Acknowledgments)
  └─ acknowledgment_title → body
附录 (Appendix)
  └─ appendix_title → body / code / tables
作者简介 / 攻读学位期间发表论文 (Author Bio / Publications)
```

**Key heuristic**: roles appear in a predictable sequence. Use surrounding context
(from sliding-window batches) to confirm your judgment. For example:
- Text right after "摘要" is likely `abstract`, not `body`.
- Text right after "参考文献" is likely `reference`, not `body`.
- A numbered line right before an image is likely a `figure_caption`.

---

## 3. Role Identification Guide

### 3.1 How to Tell Headings Apart

Chinese theses follow predictable numbering patterns. Use these heuristics:

| Role | Typical Patterns | Examples |
|---|---|---|
| `document_title` | Very first non-empty significant line of the document; usually large and bold; no numbering | "人工智能技术在文档自动化排版中的应用研究" |
| `title_l1` | "第N章" prefix, or "1 " (single digit + space), or Chinese word headings like "摘要" "参考文献" "致谢" | "第1章 绪论", "1 研究背景", "参考文献", "致谢" |
| `title_l2` | "N.M" pattern (two levels), or "1.1 " prefix | "1.1 研究背景与意义", "2.3.1 系统设计" — wait, no — 2.3.1 is L3 |
| `title_l3` | "N.M.K" pattern (three levels), or "1.1.1 " prefix | "1.1.1 深度学习的泛化问题" |

**Important discrimination rules**:
- If a line starts with "第N章" → definitely `title_l1`.
- If a line has a 1-part number ("1 ", "2 ") AND appears to be a chapter/section title
  (short, starts a new major topic) → `title_l1`.
- If a line has a 2-part number ("1.1 ", "2.3 ") → `title_l2`.
- If a line has a 3-part number ("1.1.1 ", "2.3.4 ") → `title_l3`.
- If numbering is ambiguous (e.g., "1" could be L1 or a list), look at surrounding
  context and the heading's length and content. Short lines that introduce new
  topics are headings; longer lines or items within a list are `list_item`.
- Chinese unnumbered chapter-like titles ("摘要", "Abstract", "目录", "参考文献",
  "致谢", "附录", "结论") are `title_l1` when they appear as major section headers.

### 3.2 How to Identify Body Text vs. Other Roles

- **`body`**: The default role for paragraphs that form the main narrative.
  Typically 2+ lines of continuous prose, first-line indented, no special markers.
- **`abstract`**: Paragraphs that appear in the abstract section. They come right
  after the "摘要" (or "Abstract") heading and before the "关键词" (or "Keywords")
  line or the next chapter. Abstract text is typically shorter than chapter body
  text and summarizes the whole work.
- **`quote`**: Indented block of text that is quoted from another source.
  Often starts with quotation marks ("" or '') or is visibly indented from both sides.
  May include a source attribution at the end. Distinguish from `body` by indentation
  level, quotation marks, or explicit "例如：" / "如下：" introductions.
- **`list_item`**: A line that starts with a bullet (•, -, \*), a number followed
  by "." or ")", a letter, or a Chinese ordinal (一、二、三、). Key distinction
  from headings: list items are part of body content, not section titles.
  If a numbered line is followed by more similarly-numbered lines of similar length,
  it is probably a `list_item`. If it stands alone and starts a new topic section,
  it is probably a `title_l2` or `title_l3`.

### 3.3 How to Identify Figure / Table / Formula Related Roles

- **`figure`**: A paragraph that contains an image (`has_image = true`). The text
  may be empty or may contain just the image marker. These are usually centered.
- **`figure_caption`**: A line that serves as the caption for a figure.
  **Always appears immediately after (or sometimes before) a figure paragraph.**
  Typical patterns: starts with "图N", "Figure N", "Fig. N", followed by a colon
  or period and the caption text. Examples: "图1-1 系统整体架构示意图",
  "Figure 3.2: Training loss curve". The caption is usually shorter than body text
  and centered.
- **`table`**: A paragraph that contains a table (`has_table = true`).
- **`table_caption`**: A line that serves as the caption for a table.
  **Always appears immediately before (or sometimes after) a table paragraph.**
  Typical patterns: starts with "表N", "Table N", followed by a colon or period
  and the caption text. Examples: "表2-1 实验结果对比", "Table 4.3: Parameter settings".
  Table captions are usually above the table in Chinese theses.
- **`formula`**: A paragraph that contains a mathematical formula (`has_formula = true`).
  May also be a line that is clearly a standalone equation even if `has_formula`
  is not set (e.g., a line containing only "E = mc²" or an equation number like "(2-1)").
  Formulas are typically centered, often with an equation number on the right.
  **Never modify the formula content itself — only change paragraph-level properties.**

### 3.4 How to Identify References

**`reference`**: Bibliography entries at the end of the thesis.
Key identifying features:
- Appear after the "参考文献" (References) heading.
- Each entry starts with a number in brackets: "[1]", "[2]", etc.
- Or starts with author names followed by title, journal/conference, year.
- Often uses a hanging indent (first line outdented, rest indented).
- Contains patterns like "et al.", "Vol.", "No.", "pp.", "DOI:", URLs, etc.
- In Chinese theses, references may be in Chinese, English, or mixed.

Example patterns:
```
[1] 张三, 李四. 深度学习在自然语言处理中的应用[J]. 计算机学报, 2023, 46(3): 456-478.
[2] LeCun Y, Bengio Y, Hinton G. Deep learning[J]. Nature, 2015, 521(7553): 436-444.
[3] 王五. 基于Transformer的图像分类方法研究[D]. 北京: 清华大学, 2022.
```

### 3.5 How to Identify Cover Info Lines

**`cover_info`**: Lines on the cover page that use space-based alignment for layout.
These are NOT semantic paragraphs — they are layout elements.

Key identifying features:
- Appear at the very beginning of the document (before the abstract).
- Follow patterns like "标题：内容" with many spaces in between.
- Use spaces to align values into columns.
- Common labels: "论文题目", "作者姓名", "学号", "学院", "专业", "指导教师",
  "Name:", "Student ID:", "Supervisor:", etc.

**Critical rule for `cover_info`**: Do NOT change alignment, font, or indent.
The original spacing layout must be preserved. You MAY normalize font size to 12pt
only if the original appears inconsistent (different sizes across cover lines).

---

## 4. Complete Role Definitions and Style Rules

### 4.1 document_title (论文题目 / Thesis Title)

**Description**: The main title of the whole document. It is the single most
important heading — there is exactly one document title per thesis/paper (or
two if there is both a Chinese and English title). It typically appears on the
cover page, possibly preceded by several empty paragraphs (blank lines) used
for vertical positioning.

**Identification cues** (the strongest signals come first):
1. **It is the overall title of the entire work**, not a chapter or section title.
   - It describes the whole paper/thesis topic, not a sub-topic
   - Examples: "人工智能技术在文档自动化排版中的应用研究", "生产实习报告",
     "基于深度学习的图像分类方法研究"
2. **No numbering**. Document titles never have chapter numbers, section numbers,
   or any other ordinal prefix. They are NOT "1 xxx", NOT "第1章 xxx".
   - **This is the key distinction from `title_l1`**: if a line starts with
     a number like "1 " or "第1章", it is `title_l1`, NOT `document_title`.
3. **Appears at the very beginning of the document** — near the top, before
   any cover info lines, abstract, table of contents, or chapters.
   - It may NOT be the absolute first line — there are often empty paragraphs
     (blank lines) before it for vertical centering. Ignore empty lines and
     look at the first few non-empty significant paragraphs.
4. **Typically centered and bold**, with a large font size.
5. **Often followed by cover info lines** (作者、学号、专业等) or directly
   by the abstract/chapter content.
6. **If there are both Chinese and English titles**, both are `document_title`
   (the English one may be slightly smaller — still use the same role but set
   confidence slightly lower if unsure).

**What it is NOT**:
- NOT "第1章 绪论" — that is `title_l1`
- NOT "1 研究背景" — that is `title_l1`
- NOT "摘要" or "参考文献" — those are `title_l1` (unnumbered section headings)
- NOT a cover info line like "姓名：张三" — that is `cover_info`

**Edge cases**:
- For a simple document like a "实习报告" with no chapters: the main title
  at the top is still `document_title`, not `title_l1`. Even if the document
  has no chapter structure, the overall title is a `document_title`.
- If the document starts with several empty paragraphs, skip past them to find
  the first significant heading — that is likely `document_title`.

**Style rules**:
- East Asian font: 黑体 (SimHei)
- Latin font: Times New Roman
- Font size: 22pt (二号)
- Bold: yes
- Alignment: center
- First line indent: 0
- Space before: 24pt
- Space after: 24pt

---

### 4.2 title_l1 (一级标题 / Level-1 Heading / Chapter)

**Description**: Major section headings within the document. Chapters, or
top-level sections. These are the highest-level structural headings AFTER the
document title.

**Identification cues** (strongest signals first):
1. **Has chapter/section numbering**:
   - "第N章" prefix (e.g., "第1章 绪论", "第三章 系统设计")
   - 1-part numbered: "1 ", "2 ", etc. (when chapters use simple numbering)
   - **If it starts with a number or "第N章", it is definitely title_l1,
     NOT document_title.**
2. **Unnumbered section titles** that mark major structural sections:
   "摘要", "Abstract", "目录", "参考文献", "致谢", "附录", "结论",
   "总结与展望", "引言", "绪论"
   - These appear AFTER the document title / cover page
   - They divide the document into major sections
3. **Short text** (usually 4-20 characters)
4. **Appears at the start of a new major section**
5. **Typically bold, larger than body text**
6. **Followed by body text or lower-level headings** (title_l2, title_l3)

**What it is NOT**:
- NOT the overall thesis/paper title — that is `document_title`
  - If a line is the main topic of the ENTIRE document and has no numbering
    and appears at the very beginning, it is probably `document_title`
- NOT a sub-section heading — that is `title_l2` or `title_l3`
- NOT a list item — list items are part of body content, not section titles

**Key discrimination from document_title**:
- `document_title` = the name of the whole work (e.g., "基于深度学习的图像分类研究")
- `title_l1` = a chapter/section within the work (e.g., "1 研究背景", "第1章 绪论")
- If it has a number (1, 第1章, 一、), it is `title_l1`
- If it has no number and is the overall topic at the top of the document,
  it is `document_title`

**Style rules**:
- East Asian font: 黑体 (SimHei)
- Latin font: Times New Roman
- Font size: 16pt (三号)
- Bold: yes
- Alignment: left
- First line indent: 0
- Space before: 18pt
- Space after: 12pt
- Line spacing: 1.5

---

### 4.3 title_l2 (二级标题 / Level-2 Heading)

**Description**: Sub-section headings within a chapter or major section.

**Identification cues**:
- 2-part numbered pattern: "1.1 ", "2.3 ", "3.10 ", etc.
- Or "1.1.1" — NO, that's L3. L2 is always exactly "N.M"
- Short text (usually 4-30 characters)
- Bold, smaller than L1 but larger than body text
- Introduces a sub-topic within the current chapter
- Followed by body text, L3 headings, or figures/tables

**Style rules**:
- East Asian font: 黑体 (SimHei)
- Latin font: Times New Roman
- Font size: 14pt (四号)
- Bold: yes
- Alignment: left
- First line indent: 0
- Space before: 12pt
- Space after: 6pt
- Line spacing: 1.5

---

### 4.4 title_l3 (三级标题 / Level-3 Heading)

**Description**: Sub-sub-section headings. The lowest numbered heading level.

**Identification cues**:
- 3-part numbered pattern: "1.1.1 ", "2.3.4 ", etc.
- Short text
- May or may not be bold (varies by template)
- Introduces a specific sub-topic within an L2 section
- Usually followed directly by body text

**Style rules**:
- East Asian font: 黑体 (SimHei)
- Latin font: Times New Roman
- Font size: 12pt (小四)
- Bold: yes
- Alignment: left
- First line indent: 0
- Space before: 6pt
- Space after: 6pt
- Line spacing: 1.5

---

### 4.5 body (正文 / Main Body Paragraph)

**Description**: The default role for narrative prose paragraphs that form the
main content of the thesis.

**Identification cues**:
- Continuous prose, usually 2+ lines
- First line indented (2 characters)
- No special markers (no heading numbers, no brackets, no figure/table prefixes)
- Makes up the majority of the document content
- Follows headings or other body paragraphs

**Style rules**:
- East Asian font: 宋体 (SimSun)
- Latin font: Times New Roman
- Font size: 12pt (小四)
- Bold: no (default off; if some runs are already bold for emphasis, leave them)
- Alignment: justify (两端对齐)
- First line indent: 2 characters
- Line spacing: 1.5
- Space before: 0pt
- Space after: 0pt

**Note on bold/italic within body**: Do NOT set bold or italic at the paragraph
level for `body`. Emphasis within body text (e.g., a term defined in bold) is
run-level formatting that should be preserved from the original.

---

### 4.6 abstract (摘要 / Abstract Paragraph)

**Description**: Paragraphs in the abstract section (Chinese or English).

**Identification cues**:
- Appears immediately after the "摘要" or "Abstract" heading
- Before the "关键词" or "Keywords" line, or before the next major section (目录/第一章)
- Summarizes the research: background, method, results, conclusion
- Typically 1-5 paragraphs long
- May be in Chinese or English
- Similar in appearance to body text but in a dedicated section

**Style rules**:
- East Asian font: 宋体 (SimSun)
- Latin font: Times New Roman
- Font size: 10.5pt (五号)
- Alignment: justify
- First line indent: 2 characters
- Line spacing: 1.5
- Space before: 6pt
- Space after: 6pt

---

### 4.7 Keywords Line (关键词行 — part of `abstract` role)

**Note**: The keyword line (e.g., "关键词：深度学习；神经网络；图像分类") is
labeled as `abstract` role, not a separate role. It shares the same formatting
as the abstract body. Treat it as the last paragraph(s) of the abstract section.

**Identification cues**:
- Appears at the end of the abstract section
- Starts with "关键词：" or "Keywords: "
- Followed by 3-8 keywords separated by semicolons or commas
- Usually a single line, sometimes two
- The "关键词" label itself is often bold at the run level — preserve that
  formatting (do not set paragraph-level bold)

**Style rules**: Same as `abstract` (see 4.6). No additional changes needed.
The keyword line uses the same 10.5pt 宋体, 2-char first-line indent, etc.

---

### 4.8 cover_info (封面信息行 / Cover Page Info Line)

**Description**: Layout lines on the cover page that use spaces for alignment.

**Identification cues**: See Section 3.5.

**Style rules**:
- **Change as little as possible.** Cover pages are hand-formatted and rely on
  exact spacing.
- Font size: 12pt (小四) — ONLY normalize if the original is inconsistent.
  If all cover lines have consistent sizing, leave them alone.
- Alignment: DO NOT CHANGE
- Indent: DO NOT CHANGE
- Font: DO NOT CHANGE
- **If in doubt, set style to `{}` (change nothing).**

---

### 4.9 figure (图片段落 / Image Paragraph)

**Description**: A paragraph that contains an image/figure.

**Identification cues**:
- `has_image = true` is the strongest signal
- May have no text, or may have the image inline with text
- Usually appears near related body text that discusses the figure
- Usually followed by a `figure_caption`

**Style rules**:
- Alignment: center
- First line indent: 0
- Space before: 6pt
- Space after: 0pt

**IMPORTANT**: Never modify the image itself — only paragraph-level alignment
and spacing.

---

### 4.10 figure_caption (图题 / Figure Caption)

**Description**: The caption text below (or above) a figure.

**Identification cues**:
- Immediately follows (or precedes) a `figure` paragraph
- Starts with "图N", "Figure N", or "Fig. N"
- Followed by a colon, period, or space, then the caption text
- Examples: "图1 系统架构图", "图2-3 训练损失曲线",
  "Figure 4.5: Example output", "Fig. 2.1 Overview of the model"
- Usually centered
- Usually shorter than body text

**Style rules**:
- East Asian font: 宋体 (SimSun)
- Latin font: Times New Roman
- Font size: 10.5pt (五号)
- Bold: yes
- Alignment: center
- First line indent: 0
- Line spacing: 1.25
- Space before: 0pt
- Space after: 12pt

---

### 4.11 table (表格段落 / Table Paragraph)

**Description**: A paragraph that contains a table.

**Identification cues**:
- `has_table = true` is the strongest signal
- Usually preceded by a `table_caption`
- Usually appears in the context of data presentation

**Style rules**:
- Alignment: center
- First line indent: 0
- Space before: 0pt
- Space after: 0pt

**IMPORTANT**: Never modify table structure, cell content, or internal formatting.
Only change paragraph-level alignment.

---

### 4.12 table_caption (表题 / Table Caption)

**Description**: The caption text above (or below) a table.

**Identification cues**:
- Immediately precedes (or sometimes follows) a `table` paragraph
- Starts with "表N", "Table N", or "Tab. N"
- Followed by a colon, period, or space, then the caption text
- Examples: "表1 实验数据对比", "表3-2 参数设置",
  "Table 5.1: Performance comparison"
- Usually centered
- Usually above the table in Chinese academic formatting

**Style rules**:
- East Asian font: 宋体 (SimSun)
- Latin font: Times New Roman
- Font size: 10.5pt (五号)
- Bold: yes
- Alignment: center
- First line indent: 0
- Line spacing: 1.25
- Space before: 12pt
- Space after: 0pt (or 6pt — caption sits right on top of the table)

---

### 4.13 reference (参考文献条目 / Bibliography Entry)

**Description**: A single reference entry in the bibliography section.

**Identification cues**: See Section 3.4.

**Style rules**:
- East Asian font: 宋体 (SimSun)
- Latin font: Times New Roman
- Font size: 10.5pt (五号)
- Alignment: left
- First line indent: 0
- Left indent: 21pt (creates hanging indent — first line sticks out left)
- Line spacing: 1.25
- Space before: 3pt
- Space after: 3pt

**Hanging indent explanation**: Each reference entry starts with "[1]" at the
left margin, and subsequent lines of the same entry are indented by 21pt.
This is achieved by setting `left_indent_pt = 21` and `first_line_indent_chars = 0`
(no additional first-line indent — the left indent handles the hanging effect).

---

### 4.14 list_item (列表项 / Numbered or Bulleted List Item)

**Description**: An item in a numbered or bulleted list within body text.

**Identification cues**:
- Starts with a bullet: •, -, \*, ◦, ▪, etc.
- Starts with a number: "1. ", "2) ", "(3) ", etc.
- Starts with a Chinese ordinal: "一、", "二、", "（一）", "（二）", etc.
- Starts with a letter: "a) ", "A. ", etc.
- Multiple consecutive lines share the same list pattern
- Lines are typically shorter than full body paragraphs
- Part of body content (not section headings)

**Discrimination from headings**:
- If the numbered lines are followed by more similar numbered lines = `list_item`
- If the line stands alone and introduces a new section with body text below = heading
- List items are part of the narrative flow; headings define structure

**Style rules**:
- East Asian font: 宋体 (SimSun)
- Latin font: Times New Roman
- Font size: 12pt (小四)
- Alignment: left
- First line indent: 0
- Left indent: 21pt
- Line spacing: 1.5
- Space before: 0pt
- Space after: 0pt

---

### 4.15 quote (引用 / Quoted Block)

**Description**: A block of text quoted from another source, set apart from
the main body.

**Identification cues**:
- Visibly indented from the left (and sometimes right)
- Often starts and ends with quotation marks
- May be introduced by "：" (colon) in the preceding paragraph
- May have a source attribution at the end
- Different font (often 楷体/KaiTi in Chinese theses)
- Longer than a single sentence — a full paragraph block

**Style rules**:
- East Asian font: 楷体 (KaiTi)
- Latin font: Times New Roman
- Font size: 11pt
- Alignment: justify
- First line indent: 2 characters
- Left indent: 21pt
- Line spacing: 1.5
- Space before: 6pt
- Space after: 6pt

---

### 4.16 formula (公式 / Formula / Equation Paragraph)

**Description**: A paragraph containing a displayed mathematical formula or equation.

**Identification cues**:
- `has_formula = true` is the strongest signal (detects OMML math)
- A line that is clearly an equation: contains math symbols, variables, etc.
- Often centered, with an equation number on the right like "(2-1)", "(3.2)", "(1)"
- Standalone — not inline with body text
- Examples: "E = mc²", a matrix, a summation formula, etc.

**Style rules**:
- Alignment: center
- First line indent: 0
- Line spacing: 1.5
- Space before: 6pt
- Space after: 6pt

**CRITICAL**: Never modify the formula content, OMML structure, or equation
numbering. Only change paragraph-level properties (alignment, spacing).
If the original formula has a number on the right, do not break that layout.

---

### 4.17 Acknowledgment Body (致谢正文 — `body` role)

**Note**: The text in the acknowledgment / 致谢 section is labeled as `body` role,
not a separate role. It follows the same formatting rules as main body text.

**Identification cues**:
- Appears after the "致谢" heading (which is `title_l1`)
- Before references or appendix
- Personal tone: thanks to advisor, family, lab mates, funding agencies
- Similar in format to body text but in a dedicated section

**Style rules**: Same as `body` (see 4.5). 12pt 宋体, justified, 2-char indent, 1.5 line spacing.

---

### 4.18 unknown (无法确定 / Cannot Determine Role)

**Description**: Use this role when you cannot confidently classify a paragraph.

**When to use `unknown`**:
- The paragraph is ambiguous and could be two or more different roles
- The paragraph is a structural element you don't recognize (page number,
  header, footer, separator line, etc.)
- Confidence would be below 0.6 for any specific role
- Empty paragraphs or whitespace-only paragraphs
- The text is garbled, corrupted, or unintelligible

**Style rules**:
- Change NOTHING. Keep the original formatting exactly as-is.
- Set `style` to `{}` (empty object).

---

## 5. Special Cases and Edge Cases

### 5.1 Empty Paragraphs

Empty paragraphs (no text, no objects) are skipped by the labeler and left as
`unknown`. The applier leaves them untouched. This is correct behavior — empty
paragraphs are often used for spacing and should not be modified.

### 5.2 Mixed Chinese and English Text

For paragraphs with mixed Chinese and English content:
- Set `font_name_east_asian` for the Chinese font
- Set `font_name` for the Western/Latin font
- Both fonts apply at the run level to the appropriate characters
- This is standard practice in Chinese typography

### 5.3 Paragraphs with Both Text and Images/Formulas

If a paragraph has both text AND an image or formula:
- If the image/formula is the primary content and the text is just a label →
  use the appropriate figure/formula role
- If it's a body paragraph with an inline image → use `body` (most inline
  images are part of the body narrative)
- When in doubt, lean toward `body` for inline objects

### 5.4 Headings in the Table of Contents

Table of contents (TOC) entries look like headings (they have "第1章", "1.1",
etc.) but they are part of the TOC, not actual headings.

**Identification**: TOC entries appear in the "目录" section, have leader dots
(......) connecting to page numbers, and are all roughly the same indent level.

**Treatment**: Mark as `unknown` — do NOT apply heading styles. TOC formatting
is complex and should be preserved from the original. Set confidence for any
heading-role guess below 0.5 when inside the TOC section.

### 5.5 Page Headers and Footers

Headers and footers (page numbers, chapter titles in the margin, running heads)
may appear as paragraphs in some parsing modes. If you can identify them as
headers/footers (repeating text, page numbers, small font at edges), mark as
`unknown` and leave them alone.

### 5.6 Section Numbering Variations

Chinese theses use various numbering schemes:

| Scheme | L1 | L2 | L3 |
|---|---|---|---|
| Chapter-based | 第1章 / 第1章 绪论 | 1.1 / 1.1 研究背景 | 1.1.1 |
| Simple numeric | 1 / 1 引言 | 1.1 | 1.1.1 |
| Dash-based | — (rare) | 1—1 | 1—1—1 |

Use the number of dot-separated parts to determine heading level, not the
absolute number. "2.3" is always L2; "2.3.1" is always L3.

### 5.7 English Abstract Section

If the document has an English abstract after the Chinese one:
- "Abstract" heading → `title_l1` (if standalone) or treat the English abstract
  as part of the abstract section
- English abstract paragraphs → `abstract`
- "Keywords:" line → `abstract` (part of the abstract section, same styling)
- Apply the same font/size rules; English text uses `font_name` (Times New Roman)

### 5.8 Appendix Sections

Appendix headings:
- "附录" or "Appendix" → `title_l1`
- "附录A" / "A.1" → treat as L2/L3 using the same numbering logic
- Appendix body text → `body` (same rules as main body)

### 5.9 Code Blocks / Algorithm Listings

If the thesis contains code blocks or algorithm listings:
- If they are in a special environment (like an algorithm float) → `unknown`
  (preserve original formatting)
- If they are just indented monospaced text → could be `quote` or `unknown`
  depending on context. When unsure, `unknown` is safer.

### 5.10 Single-Line Paragraphs

Very short single-line paragraphs (1-10 characters) are often ambiguous.
Consider:
- Could it be a heading? Check for numbering patterns.
- Could it be a caption? Check if it's near a figure/table.
- Could it be a list item? Check surrounding lines.
- If none of the above → `body` (it might just be a short paragraph)
  or `unknown` if truly ambiguous.

---

## 6. Style Property Reference

### 6.1 Chinese Font Size Reference (字号对照表)

Chinese typography uses a traditional "号" (hào) system. Here is the
standard mapping to points:

| 号数 (Hào) | Points (pt) | Common Usage |
|---|---|---|
| 初号 | 42pt | Very large titles (rare) |
| 小初 | 36pt | Extra-large titles |
| 一号 | 26pt | Large section titles |
| 小一 | 24pt | |
| 二号 | 22pt | Thesis main title |
| 小二 | 18pt | |
| 三号 | 16pt | Level-1 headings |
| 小三 | 15pt | |
| 四号 | 14pt | Level-2 headings |
| 小四 | 12pt | Body text, Level-3 headings |
| 五号 | 10.5pt | Captions, references, abstract |
| 小五 | 9pt | Footnotes, small text |
| 六号 | 7.5pt | Very small text |

**Rule**: When the rules specify a font size in pt, use that exact value.
The 号数 reference is for your understanding of Chinese typographic conventions.

### 6.2 Common Chinese Font Names

| Chinese Name | English Name | Typical Usage |
|---|---|---|
| 宋体 | SimSun / Song | Body text (standard serif) |
| 黑体 | SimHei / Heiti | Headings (sans-serif) |
| 楷体 | KaiTi | Quotes, acknowledgments |
| 仿宋 | FangSong | Government documents, quotes |
| 微软雅黑 | Microsoft YaHei | Modern sans-serif (less common in theses) |

### 6.3 Indentation Units

- **First line indent in characters**: "2 characters" means the first line
  starts 2 × font-size to the right. For 12pt font, that's 24pt.
  This is the standard way Chinese typography specifies paragraph indent.
- **Left indent in points**: Absolute indent from the left margin.
  Used for hanging indents (references) and block quotes.

### 6.4 Alignment Values

- `left` — left-aligned (ragged right)
- `center` — centered
- `right` — right-aligned
- `justify` — justified / 两端对齐 (both left and right edges align;
  standard for body text in Chinese theses)

---

## 7. Confidence Guidelines

Assign `confidence` honestly. The system rejects labels below 0.6 and leaves
those paragraphs unchanged (which is the safe default).

**High confidence (0.9 - 1.0)**: Clear, unambiguous signals.
- A heading with "第1章" prefix → 0.98
- A paragraph after "摘要" heading that looks like abstract text → 0.9
- A reference starting with "[1]" in the references section → 0.95
- A paragraph with `has_image=true` → 0.99 for `figure`
- Caption starting with "图1" right after an image → 0.95

**Medium confidence (0.7 - 0.89)**: Good signals but some ambiguity.
- A short bold line that might be L3 or just emphasized text → 0.75
- A paragraph that could be body or abstract, near a section boundary → 0.7
- A line that might be a list item or a heading → 0.75

**Low confidence (0.5 - 0.69)**: Significant uncertainty.
- An isolated short line with no context → 0.55
- Something that could be two very different roles → 0.5-0.6
- If your confidence is below 0.6, the system will ignore your label anyway,
  so only assign a role below 0.6 if you're making your best guess and want
  it recorded in the annotation.

**When to just use `unknown`**:
- If you truly cannot tell what something is
- If the paragraph is garbled or empty
- If it could equally be 3+ different roles
- If confidence would be below 0.5

---

## 8. Summary Table of All Role Styles

Quick reference. For each role, only the explicitly-set properties are shown.
Properties not listed for a role are left unchanged from the original document.

| Role | EA Font | Latin Font | Size | Bold | Align | Indent (1st) | Left Indent | Line Space | Space Before | Space After |
|---|---|---|---|---|---|---|---|---|---|---|
| **document_title** | 黑体 | TNR | 22pt | yes | center | 0 | — | — | 24pt | 24pt |
| **title_l1** | 黑体 | TNR | 16pt | yes | left | 0 | — | 1.5 | 18pt | 12pt |
| **title_l2** | 黑体 | TNR | 14pt | yes | left | 0 | — | 1.5 | 12pt | 6pt |
| **title_l3** | 黑体 | TNR | 12pt | yes | left | 0 | — | 1.5 | 6pt | 6pt |
| **body** | 宋体 | TNR | 12pt | — | justify | 2 char | — | 1.5 | 0 | 0 |
| **abstract** | 宋体 | TNR | 10.5pt | — | justify | 2 char | — | 1.5 | 6pt | 6pt |
| **cover_info** | — | — | (12pt*) | — | — | — | — | — | — | — |
| **figure** | — | — | — | — | center | 0 | — | — | 6pt | 0 |
| **figure_caption** | 宋体 | TNR | 10.5pt | yes | center | 0 | — | 1.25 | 0 | 12pt |
| **table** | — | — | — | — | center | 0 | — | — | 0 | 0 |
| **table_caption** | 宋体 | TNR | 10.5pt | yes | center | 0 | — | 1.25 | 12pt | 0 |
| **reference** | 宋体 | TNR | 10.5pt | — | left | 0 | 21pt | 1.25 | 3pt | 3pt |
| **list_item** | 宋体 | TNR | 12pt | — | left | 0 | 21pt | 1.5 | 0 | 0 |
| **quote** | 楷体 | TNR | 11pt | — | justify | 2 char | 21pt | 1.5 | 6pt | 6pt |
| **formula** | — | — | — | — | center | 0 | — | 1.5 | 6pt | 6pt |
| **unknown** | — | — | — | — | — | — | — | — | — | — |

*Cover info: only normalize font size if original is inconsistent. Otherwise change nothing.
"TNR" = Times New Roman.
"—" means "do not change / not specified" (leave original formatting).

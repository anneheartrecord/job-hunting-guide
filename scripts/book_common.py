"""PDF 和 EPUB 共用的书籍内容、样式与 Markdown 转换。"""

import html
import re
from datetime import date
from pathlib import Path

import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.sane_lists import SaneListExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension, slugify_unicode
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TITLE = "求职系列"
ENGLISH_TITLE = "JOB HUNTING GUIDE"
AUTHOR = "anneheartrecord"
LANGUAGE = "zh-CN"
LICENSE = "MIT License"
SUBTITLE = "大厂工程师的求职方法论：从简历到谈薪，全流程拆解"
WEBSITE = f"https://{AUTHOR}.github.io/job-hunting-guide/"
REPOSITORY = f"https://github.com/{AUTHOR}/job-hunting-guide"

BOOK_CSS = """
* { box-sizing: border-box; }
body {
  font-family: "PingFang SC", "Noto Sans CJK SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.85; color: #1f2937;
}
.cover .tag { color: #3b82f6; letter-spacing: 0.3em; }
.cover h1 { line-height: 1.2; color: #0f172a; border: none; }
.cover .sub { color: #475569; }
.cover .bar { background: #3b82f6; }
.cover .chapters { color: #334155; line-height: 2.1; }
.cover .meta { color: #64748b; line-height: 1.9; }
.front h2 { color: #0f172a; }
.toc { list-style: none; padding: 0; }
.toc > li > a { font-weight: 600; color: #0f172a; text-decoration: none; }
.toc ul, .toc ol { list-style: none; }
.toc ul li, .toc ol li { line-height: 1.7; }
.toc ul a, .toc ol a { color: #475569; text-decoration: none; }
.chapter h1 { line-height: 1.4; color: #0f172a; border-bottom: 2px solid #3b82f6; }
.chapter h2 { color: #0f172a; break-after: avoid; }
.chapter h3 { color: #1e293b; break-after: avoid; }
p { text-align: justify; }
strong { color: #0f172a; }
blockquote { border-left: 3px solid #93c5fd; background: #f1f5f9; color: #334155; }
blockquote p:last-child { margin-bottom: 0; }
hr { border: none; border-top: 1px solid #e2e8f0; }
img { display: block; max-width: 100%; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; break-inside: auto; }
th, td { border: 1px solid #cbd5e1; text-align: left; vertical-align: top; }
th { background: #eff6ff; color: #0f172a; }
tr { break-inside: avoid; }
code { font-family: "SF Mono", Menlo, monospace; background: #f1f5f9; }
a { color: #2563eb; }
"""

PREFACE = """
  <p>这是在职大厂工程师的一套求职方法论。从实习、校招到社招，累计面试上百场，校招拿到多个大厂 offer，近期社招通过率超过 90%；从本科开始辅导学弟学妹，毕业后陆续辅导了数十位不同背景的同学，覆盖暑期实习、秋招春招、社招跳槽、技术转型和发展路线规划。</p>
  <p>同样的问题回答了太多遍，于是整理成这个系列开源。它不是泛泛的鸡汤，是可以直接拿去用的操作指南，适合正在准备校招或社招的工程师、想从小厂跳大厂的人、简历投了很多但面试机会很少的人，以及想系统提升面试通过率的人。</p>"""


def render_markdown(path: Path, *, for_epub: bool = False) -> tuple[str, list[dict]]:
    extensions = [TableExtension(), SaneListExtension()]
    if for_epub:
        extensions.extend([TocExtension(slugify=slugify_unicode), FencedCodeExtension()])
    else:
        extensions.append(TocExtension())
    md = markdown.Markdown(extensions=extensions)
    return md.convert(path.read_text(encoding="utf-8")), md.toc_tokens


def save_jpeg(image: Image.Image, output: Path) -> None:
    image = image.convert("RGB")
    image.thumbnail((1400, 1400))
    image.save(output, "JPEG", quality=82, optimize=True)


def edition_label() -> str:
    return f"合集版本：{date.today():%Y-%m}　·　{LICENSE}"


def cover_page(titles: list[str]) -> str:
    short = [re.sub(r"^求职系列（\d+）：", "", title) for title in titles]
    chapter_list = "<br />".join(f"{i:02d}　{html.escape(title)}" for i, title in enumerate(short, start=1))
    return f"""
<section class="cover">
  <div class="tag">{ENGLISH_TITLE}</div>
  <h1>{TITLE}</h1>
  <div class="sub">{SUBTITLE}</div>
  <div class="bar"></div>
  <div class="chapters">{chapter_list}</div>
  <div class="meta">
    作者：{AUTHOR}<br />
    在线阅读：{WEBSITE}<br />
    仓库：{REPOSITORY}<br />
    {edition_label()}
  </div>
</section>"""

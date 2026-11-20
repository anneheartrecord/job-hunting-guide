# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown>=3.5", "pillow>=10", "playwright==1.63.0"]
# ///
"""把 docs/ 下的求职系列文章合成一份 PDF。

用法（在仓库根目录）：
    uv run scripts/build_pdf.py
首次运行如提示缺浏览器，先执行 `uv run --with playwright==1.63.0 playwright install chromium`。
输出：求职系列.pdf
"""

import html
import re
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from book_common import (
    BOOK_CSS,
    DOCS,
    LANGUAGE,
    PREFACE,
    ROOT,
    TITLE,
    cover_page,
    render_markdown,
    save_jpeg,
)

IMGS = ROOT / "imgs"
OUTPUT = ROOT / f"{TITLE}.pdf"

CSS = BOOK_CSS + """
@page { size: A4; margin: 22mm 20mm 20mm 20mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-size: 10.5pt; margin: 0; }
.cover {
  height: 250mm; display: flex; flex-direction: column; justify-content: center;
  padding: 0 6mm; break-after: page;
}
.cover .tag { font-size: 12pt; margin-bottom: 8mm; }
.cover h1 { font-size: 46pt; margin: 0 0 6mm; }
.cover .sub { font-size: 15pt; margin-bottom: 18mm; }
.cover .bar { width: 28mm; height: 2.4mm; border-radius: 1.2mm; margin-bottom: 18mm; }
.cover .chapters { font-size: 11pt; }
.cover .meta { margin-top: auto; font-size: 9.5pt; }
.front { break-after: page; }
.front h2 { font-size: 18pt; margin: 0 0 4mm; }
.front p { margin: 0 0 3mm; }
.toc { margin: 0 0 10mm; }
.toc > li { margin: 0 0 3mm; }
.toc > li > a { font-size: 11.5pt; }
.toc ul { padding-left: 7mm; margin: 1mm 0 0; }
.toc ul li { font-size: 9.5pt; }
.chapter { break-before: page; }
.chapter h1 { font-size: 20pt; margin: 0 0 8mm; padding-bottom: 4mm; }
.chapter h2 { font-size: 14.5pt; margin: 9mm 0 3mm; }
.chapter h3 { font-size: 12pt; margin: 6mm 0 2mm; }
p { margin: 0 0 3.2mm; }
ul, ol { padding-left: 6mm; margin: 0 0 3.2mm; }
li { margin: 0 0 1.2mm; }
blockquote { margin: 0 0 4mm; padding: 2.5mm 5mm; border-radius: 0 2mm 2mm 0; }
hr { margin: 6mm 0; }
img { max-height: 120mm; margin: 4mm auto; border-radius: 3mm; }
table { margin: 0 0 4mm; font-size: 9.5pt; }
th, td { padding: 1.8mm 2.5mm; }
code { font-size: 9pt; padding: 0 1mm; border-radius: 1mm; }
"""

FOOTER = (
    '<div style="width:100%;font-size:8px;color:#94a3b8;padding:0 20mm;'
    'font-family:PingFang SC,sans-serif;display:flex;justify-content:space-between;">'
    "<span>求职系列 · Job Hunting Guide</span>"
    '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
)


def shrink_images(tmp: Path) -> dict[str, Path]:
    """PNG 原图单张 1MB+，转成 1400px 宽的 JPEG 再嵌入，控制 PDF 体积。"""
    mapping = {}
    for png in sorted(IMGS.glob("*.png")):
        out = tmp / f"{png.stem}.jpg"
        with Image.open(png) as im:
            save_jpeg(im, out)
        mapping[png.name] = out
    return mapping


def render_chapter(idx: int, path: Path, images: dict[str, Path]) -> tuple[str, str, list[tuple[str, str]]]:
    body, headings = render_markdown(path)
    prefix = f"c{idx}-"
    body = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}{m.group(1)}"', body)

    def fix_img(m: re.Match) -> str:
        name = Path(m.group(1)).name
        return f'src="{images[name].as_uri()}"' if name in images else m.group(0)

    body = re.sub(r'src="([^"]+)"', fix_img, body)

    title, sections = path.stem, []
    for tok in headings:
        if tok["level"] == 1:
            title = html.unescape(tok["name"])
            anchor = prefix + tok["id"]
            sections = [(prefix + c["id"], html.unescape(c["name"])) for c in tok["children"]]
            break
    else:
        anchor = f"{prefix}top"
        body = f'<a id="{anchor}"></a>' + body
    return f'<section class="chapter">{body}</section>', title, [(anchor, title)] + sections


def build_html(images: dict[str, Path]) -> str:
    chapters, toc_items, titles = [], [], []
    for idx, path in enumerate(sorted(DOCS.glob("*.md")), start=1):
        body, title, entries = render_chapter(idx, path, images)
        chapters.append(body)
        titles.append(title)
        (anchor, _), subs = entries[0], entries[1:]
        sub_html = "".join(f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a, t in subs)
        toc_items.append(
            f'<li><a href="#{anchor}">{html.escape(title)}</a>'
            + (f"<ul>{sub_html}</ul>" if sub_html else "")
            + "</li>"
        )

    front = f"""
<section class="front">
  <h2>写在前面</h2>{PREFACE}
  <p>本 PDF 由仓库 <code>docs/</code> 下的 {len(titles)} 篇文章自动合成，按求职流程排序：先写简历，再理解面试、准备面试、打磨自我介绍，然后决定怎么跳、怎么谈薪，最后处理答不上来的场面。</p>
  <h2 style="margin-top:9mm">目录</h2>
  <ul class="toc">{''.join(toc_items)}</ul>
</section>"""

    return (
        f'<!DOCTYPE html><html lang="{LANGUAGE}"><head><meta charset="utf-8">'
        f"<title>{TITLE} — Job Hunting Guide</title><style>{CSS}</style></head>"
        f"<body>{cover_page(titles)}{front}{''.join(chapters)}</body></html>"
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        images = shrink_images(tmp)
        page_file = tmp / "book.html"
        page_file.write_text(build_html(images), encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(page_file.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(OUTPUT),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=FOOTER,
                outline=True,
                tagged=True,
            )
            browser.close()
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()

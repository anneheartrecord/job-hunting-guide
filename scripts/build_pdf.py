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
from datetime import date
from pathlib import Path

import markdown
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
IMGS = ROOT / "imgs"
OUTPUT = ROOT / "求职系列.pdf"

CSS = """
@page { size: A4; margin: 22mm 20mm 20mm 20mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "PingFang SC", "Noto Sans CJK SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 10.5pt; line-height: 1.85; color: #1f2937; margin: 0;
}
.cover {
  height: 250mm; display: flex; flex-direction: column; justify-content: center;
  padding: 0 6mm; break-after: page;
}
.cover .tag { color: #3b82f6; font-size: 12pt; letter-spacing: 0.3em; margin-bottom: 8mm; }
.cover h1 { font-size: 46pt; line-height: 1.2; margin: 0 0 6mm; color: #0f172a; border: none; }
.cover .sub { font-size: 15pt; color: #475569; margin-bottom: 18mm; }
.cover .bar { width: 28mm; height: 2.4mm; background: #3b82f6; border-radius: 1.2mm; margin-bottom: 18mm; }
.cover .chapters { font-size: 11pt; color: #334155; line-height: 2.1; }
.cover .meta { margin-top: auto; font-size: 9.5pt; color: #64748b; line-height: 1.9; }
.front { break-after: page; }
.front h2 { font-size: 18pt; margin: 0 0 4mm; color: #0f172a; }
.front p { margin: 0 0 3mm; }
.toc { list-style: none; padding: 0; margin: 0 0 10mm; }
.toc > li { margin: 0 0 3mm; }
.toc > li > a { font-weight: 600; font-size: 11.5pt; color: #0f172a; text-decoration: none; }
.toc ul { list-style: none; padding-left: 7mm; margin: 1mm 0 0; }
.toc ul li { font-size: 9.5pt; line-height: 1.7; }
.toc ul a { color: #475569; text-decoration: none; }
.chapter { break-before: page; }
.chapter h1 {
  font-size: 20pt; line-height: 1.4; color: #0f172a; margin: 0 0 8mm;
  padding-bottom: 4mm; border-bottom: 2px solid #3b82f6;
}
.chapter h2 { font-size: 14.5pt; color: #0f172a; margin: 9mm 0 3mm; break-after: avoid; }
.chapter h3 { font-size: 12pt; color: #1e293b; margin: 6mm 0 2mm; break-after: avoid; }
p { margin: 0 0 3.2mm; text-align: justify; }
strong { color: #0f172a; }
ul, ol { padding-left: 6mm; margin: 0 0 3.2mm; }
li { margin: 0 0 1.2mm; }
blockquote {
  margin: 0 0 4mm; padding: 2.5mm 5mm; border-left: 3px solid #93c5fd;
  background: #f1f5f9; color: #334155; border-radius: 0 2mm 2mm 0;
}
blockquote p:last-child { margin-bottom: 0; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 6mm 0; }
img { display: block; max-width: 100%; max-height: 120mm; margin: 4mm auto; border-radius: 3mm; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: 0 0 4mm; font-size: 9.5pt; break-inside: auto; }
th, td { border: 1px solid #cbd5e1; padding: 1.8mm 2.5mm; text-align: left; vertical-align: top; }
th { background: #eff6ff; color: #0f172a; }
tr { break-inside: avoid; }
code { font-family: "SF Mono", Menlo, monospace; font-size: 9pt; background: #f1f5f9; padding: 0 1mm; border-radius: 1mm; }
a { color: #2563eb; }
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
            im = im.convert("RGB")
            im.thumbnail((1400, 1400))
            im.save(out, "JPEG", quality=82, optimize=True)
        mapping[png.name] = out
    return mapping


def render_chapter(idx: int, path: Path, images: dict[str, Path]) -> tuple[str, str, list[tuple[str, str]]]:
    md = markdown.Markdown(extensions=["tables", "sane_lists", "toc"])
    body = md.convert(path.read_text(encoding="utf-8"))
    prefix = f"c{idx}-"
    body = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}{m.group(1)}"', body)

    def fix_img(m: re.Match) -> str:
        name = Path(m.group(1)).name
        return f'src="{images[name].as_uri()}"' if name in images else m.group(0)

    body = re.sub(r'src="([^"]+)"', fix_img, body)

    title, sections = path.stem, []
    for tok in md.toc_tokens:
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

    short = [re.sub(r"^求职系列（\d+）：", "", t) for t in titles]
    chapter_list = "<br>".join(f"{i:02d}　{html.escape(t)}" for i, t in enumerate(short, start=1))
    cover = f"""
<section class="cover">
  <div class="tag">JOB HUNTING GUIDE</div>
  <h1>求职系列</h1>
  <div class="sub">大厂工程师的求职方法论：从简历到谈薪，全流程拆解</div>
  <div class="bar"></div>
  <div class="chapters">{chapter_list}</div>
  <div class="meta">
    作者：anneheartrecord<br>
    在线阅读：https://anneheartrecord.github.io/job-hunting-guide/<br>
    仓库：https://github.com/anneheartrecord/job-hunting-guide<br>
    合集版本：{date.today():%Y-%m}　·　MIT License
  </div>
</section>"""

    front = f"""
<section class="front">
  <h2>写在前面</h2>
  <p>这是在职大厂工程师的一套求职方法论。从实习、校招到社招，累计面试上百场，校招拿到多个大厂 offer，近期社招通过率超过 90%；从本科开始辅导学弟学妹，毕业后陆续辅导了数十位不同背景的同学，覆盖暑期实习、秋招春招、社招跳槽、技术转型和发展路线规划。</p>
  <p>同样的问题回答了太多遍，于是整理成这个系列开源。它不是泛泛的鸡汤，是可以直接拿去用的操作指南，适合正在准备校招或社招的工程师、想从小厂跳大厂的人、简历投了很多但面试机会很少的人，以及想系统提升面试通过率的人。</p>
  <p>本 PDF 由仓库 <code>docs/</code> 下的 {len(titles)} 篇文章自动合成，按求职流程排序：先写简历，再理解面试、准备面试、打磨自我介绍，然后决定怎么跳、怎么谈薪，最后处理答不上来的场面。</p>
  <h2 style="margin-top:9mm">目录</h2>
  <ul class="toc">{''.join(toc_items)}</ul>
</section>"""

    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>求职系列 — Job Hunting Guide</title><style>{CSS}</style></head>"
        f"<body>{cover}{front}{''.join(chapters)}</body></html>"
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

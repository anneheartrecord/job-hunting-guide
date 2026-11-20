# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown>=3.5", "pillow>=10"]
# ///
"""把 docs/ 下的求职系列文章合成 EPUB 3。

用法：uv run scripts/build_epub.py [-o 输出路径]
默认在仓库根目录生成 求职系列.epub。
"""

import argparse
import html
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html.entities import html5
from itertools import count
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from PIL import Image

from book_common import (
    AUTHOR,
    BOOK_CSS,
    DOCS,
    LANGUAGE,
    LICENSE,
    PREFACE,
    REPOSITORY,
    ROOT,
    SUBTITLE,
    TITLE,
    WEBSITE,
    edition_label,
    render_markdown,
    save_jpeg,
)
from epub_cover import render_epub_cover

OUTPUT = ROOT / f"{TITLE}.epub"
COVER_HREF = "images/cover.png"
NAV_HREF = "nav.xhtml"
TOC_HREF = "toc.xhtml"
NCX_HREF = "toc.ncx"
XHTML = "application/xhtml+xml"
IMAGE_TYPES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}

CSS = BOOK_CSS + """
.epub-cover img { max-height: 95vh; margin: 0 auto; border-radius: 0; }
.toc { margin: 0 0 1em; }
.toc ol { padding-left: 1.4em; margin: 0.25em 0; }
.chapter h1 { font-size: 1.65em; margin: 0 0 1em; padding-bottom: 0.5em; }
.chapter h2 { font-size: 1.25em; margin: 1.5em 0 0.5em; }
.chapter h3 { font-size: 1.1em; margin: 1.25em 0 0.4em; }
p, ul, ol { margin: 0 0 0.8em; }
ul, ol { padding-left: 1.6em; }
li { margin-bottom: 0.3em; }
blockquote { margin: 0 0 1em; padding: 0.5em 0.8em; border-radius: 0 0.3em 0.3em 0; }
hr { margin: 1.5em 0; }
img { height: auto; margin: 1em auto; border-radius: 0.3em; }
table { margin: 0 0 1em; font-size: 0.9em; }
th, td { padding: 0.3em 0.5em; overflow-wrap: break-word; }
code { padding: 0 0.2em; border-radius: 0.15em; }
pre { white-space: pre-wrap; overflow-wrap: break-word; }
"""

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="EPUB/book.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


@dataclass
class TocEntry:
    title: str
    href: str
    children: list["TocEntry"]


def xhtml(title: str, body: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      lang="{LANGUAGE}" xml:lang="{LANGUAGE}">
  <head>
    <title>{html.escape(title)}</title>
    <link rel="stylesheet" href="book.css" type="text/css" />
  </head>
  <body>{body}</body>
</html>
"""


def epub_anchor(identifier: str) -> str:
    # Some AZW3 conversions resolve Unicode links to the page start. Reserve an
    # ASCII prefix so encoded IDs cannot collide with unchanged source IDs.
    prefix = "epub-id-"
    if identifier.isascii() and not identifier.startswith(prefix):
        return identifier
    return prefix + identifier.encode("utf-8").hex()


def toc_label(title: str) -> str:
    title = re.sub(r"^([0-9])[\ufe0e\ufe0f]?\u20e3(?=\s|$)", r"\1.", title)
    return re.sub(r"([0-9#*])[\ufe0e\ufe0f]?\u20e3", r"\1", title)


def section_entries(href: str, headings: list[dict]) -> list[TocEntry]:
    return [
        TocEntry(
            toc_label(html.unescape(heading["name"])),
            f"{href}#{quote(epub_anchor(heading['id']))}",
            section_entries(href, heading["children"]),
        )
        for heading in headings
    ]


def render_toc_items(entries: list[TocEntry]) -> str:
    items = []
    for entry in entries:
        link = f'<a href="{html.escape(entry.href)}">{html.escape(entry.title)}</a>'
        children = f"<ol>{render_toc_items(entry.children)}</ol>" if entry.children else ""
        items.append(f"<li>{link}{children}</li>")
    return "".join(items)


def ncx_document(entries: list[TocEntry]) -> bytes:
    ncx = ET.Element("ncx", {
        "xmlns": "http://www.daisy.org/z3986/2005/ncx/",
        "version": "2005-1",
        "xml:lang": LANGUAGE,
    })
    head = ET.SubElement(ncx, "head")
    title = ET.SubElement(ncx, "docTitle")
    ET.SubElement(title, "text").text = TITLE
    nav_map = ET.SubElement(ncx, "navMap")
    play_order = count(1)

    def add_points(parent: ET.Element, entries: list[TocEntry], depth: int) -> int:
        max_depth = depth
        for entry in entries:
            order = next(play_order)
            point = ET.SubElement(parent, "navPoint", id=f"nav-{order}", playOrder=str(order))
            label = ET.SubElement(point, "navLabel")
            ET.SubElement(label, "text").text = entry.title
            ET.SubElement(point, "content", src=entry.href)
            if entry.children:
                max_depth = max(max_depth, add_points(point, entry.children, depth + 1))
        return max_depth

    depth = add_points(nav_map, entries, 1)
    ET.SubElement(head, "meta", name="dtb:uid", content=REPOSITORY)
    ET.SubElement(head, "meta", name="dtb:depth", content=str(depth))
    ET.SubElement(head, "meta", name="dtb:totalPageCount", content="0")
    ET.SubElement(head, "meta", name="dtb:maxPageNumber", content="0")
    ET.indent(ncx)
    return ET.tostring(ncx, encoding="utf-8", xml_declaration=True)


def chapter_fragment(body: str, source: Path) -> ET.Element:
    def numeric_entity(match: re.Match) -> str:
        value = html5.get(match[0][1:])
        return match[0] if value is None else "".join(f"&#{ord(char)};" for char in value)

    body = re.sub(r"&[a-zA-Z][a-zA-Z0-9]*;", numeric_entity, body)
    try:
        chapter = ET.fromstring(f'<section class="chapter">{body}</section>')
    except ET.ParseError as exc:
        raise ValueError(f"{source.name} 生成了无效的 XHTML：{exc}") from exc
    for element in chapter.iter():
        if identifier := element.get("id"):
            element.set("id", epub_anchor(identifier))
    return chapter


def add_image(archive: ZipFile, source: Path, number: int, staging: Path) -> tuple[str, str]:
    extension = source.suffix.lower()
    if extension not in IMAGE_TYPES:
        raise ValueError(f"EPUB 不支持此图片格式：{source.name}")
    if extension == ".png":
        with Image.open(source) as image:
            if image.n_frames == 1 and "transparency" not in image.info and "A" not in image.getbands():
                extension = ".jpg"
                source = staging / f"image-{number}.jpg"
                save_jpeg(image, source)
    href = f"images/image-{number}{extension}"
    archive.write(source, f"EPUB/{href}")
    return href, IMAGE_TYPES[extension]


def package_document(spine: list[tuple[str, str]], images: list[tuple[str, str]]) -> bytes:
    package = ET.Element("package", {
        "xmlns": "http://www.idpf.org/2007/opf",
        "version": "3.0",
        "unique-identifier": "book-id",
        "xml:lang": LANGUAGE,
    })
    metadata = ET.SubElement(package, "metadata", {"xmlns:dc": "http://purl.org/dc/elements/1.1/"})
    ET.SubElement(metadata, "dc:identifier", id="book-id").text = REPOSITORY
    ET.SubElement(metadata, "dc:title").text = TITLE
    ET.SubElement(metadata, "dc:creator").text = AUTHOR
    ET.SubElement(metadata, "dc:language").text = LANGUAGE
    ET.SubElement(metadata, "dc:description").text = SUBTITLE
    ET.SubElement(metadata, "dc:rights").text = LICENSE
    ET.SubElement(metadata, "meta", property="dcterms:modified").text = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    manifest = ET.SubElement(package, "manifest")
    ET.SubElement(manifest, "item", id="css", href="book.css", **{"media-type": "text/css"})
    ET.SubElement(manifest, "item", id="nav", href=NAV_HREF, properties="nav", **{"media-type": XHTML})
    ET.SubElement(manifest, "item", id="ncx", href=NCX_HREF, **{"media-type": "application/x-dtbncx+xml"})
    ET.SubElement(manifest, "item", {
        "id": "cover-image",
        "href": COVER_HREF,
        "media-type": "image/png",
        "properties": "cover-image",
    })
    reading_order = ET.SubElement(package, "spine", toc="ncx")
    for item_id, href in spine:
        ET.SubElement(manifest, "item", id=item_id, href=href, **{"media-type": XHTML})
        ET.SubElement(reading_order, "itemref", idref=item_id)
    for number, (href, media_type) in enumerate(images, start=1):
        ET.SubElement(manifest, "item", id=f"image-{number}", href=href, **{"media-type": media_type})

    guide = ET.SubElement(package, "guide")
    ET.SubElement(guide, "reference", type="toc", title="目录", href=TOC_HREF)
    ET.indent(package)
    return ET.tostring(package, encoding="utf-8", xml_declaration=True)


def build_epub(output: Path) -> None:
    sources = sorted(DOCS.glob("*.md"))
    if not sources:
        raise ValueError(f"{DOCS} 中没有 Markdown 文章")

    credits = (f"作者：{AUTHOR}", f"仓库：{REPOSITORY}", edition_label())
    cover_image = render_epub_cover(credits)
    cover_alt = html.escape("。".join((TITLE, SUBTITLE, *credits)))
    chapter_files = {path.resolve(): f"chapter-{i:02d}.xhtml" for i, path in enumerate(sources, start=1)}
    spine = [("cover", "cover.xhtml"), ("preface", "preface.xhtml"), ("toc", TOC_HREF)]
    toc_entries, images = [], {}

    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory)
        staged_epub = staging / "book.epub"
        with ZipFile(staged_epub, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", b"application/epub+zip", compress_type=ZIP_STORED)
            archive.writestr("META-INF/container.xml", CONTAINER)
            archive.writestr("EPUB/book.css", CSS)
            archive.writestr(f"EPUB/{COVER_HREF}", cover_image)

            for number, source in enumerate(sources, start=1):
                body, headings = render_markdown(source, for_epub=True)
                chapter = chapter_fragment(body, source)
                heading = next((item for item in headings if item["level"] == 1), None)
                if heading is None:
                    title = source.stem
                    title_element = ET.Element("h1")
                    title_element.text = title
                    chapter.insert(0, title_element)
                else:
                    title = html.unescape(heading["name"])
                    index = headings.index(heading)
                    headings[index:index + 1] = heading["children"]

                for image in chapter.iter("img"):
                    src = image.get("src", "")
                    url = urlsplit(src)
                    image_path = (source.parent / unquote(url.path)).resolve()
                    if url.scheme or url.netloc or not image_path.is_relative_to(ROOT) or not image_path.is_file():
                        raise ValueError(f"{source.name} 引用的图片无法打包：{src}")
                    if image_path not in images:
                        images[image_path] = add_image(archive, image_path, len(images) + 1, staging)
                    image.set("src", images[image_path][0])

                online_source = WEBSITE + quote(source.relative_to(ROOT).as_posix())
                for link in chapter.iter("a"):
                    href = link.get("href", "")
                    url = urlsplit(href)
                    if url.scheme or url.netloc:
                        continue
                    fragment = quote(epub_anchor(unquote(url.fragment))) if url.fragment else ""
                    if not url.path:
                        if url.fragment:
                            link.set("href", url._replace(fragment=fragment).geturl())
                        continue
                    linked_chapter = chapter_files.get((source.parent / unquote(url.path)).resolve())
                    if linked_chapter:
                        suffix = f"#{fragment}" if fragment else ""
                        link.set("href", linked_chapter + suffix)
                    else:
                        link.set("href", urljoin(online_source, href))

                href = chapter_files[source.resolve()]
                spine.append((f"chapter-{number}", href))
                toc_entries.append(TocEntry(toc_label(title), href, section_entries(href, headings)))
                archive.writestr(f"EPUB/{href}", xhtml(title, ET.tostring(chapter, encoding="unicode")))

            preface = f"""
<section class="front" epub:type="preface">
  <h1>写在前面</h1>{PREFACE}
  <p>本 EPUB 收录仓库 <code>docs/</code> 下的 {len(sources)} 篇文章，按文件名排列。</p>
</section>"""
            toc_list = f'<ol class="toc">{render_toc_items(toc_entries)}</ol>'
            toc_page = f"<h1>目录</h1>\n{toc_list}"
            nav = f"""
<nav epub:type="toc">
  {toc_page}
</nav>
<nav epub:type="landmarks" hidden="hidden">
  <ol>
    <li><a epub:type="toc" href="{TOC_HREF}">目录</a></li>
    <li><a epub:type="bodymatter" href="{toc_entries[0].href}">正文起点</a></li>
  </ol>
</nav>"""
            cover = f"""
<section class="epub-cover" epub:type="cover">
  <img src="{COVER_HREF}" alt="{cover_alt}" />
</section>"""
            archive.writestr("EPUB/cover.xhtml", xhtml(TITLE, cover))
            archive.writestr("EPUB/preface.xhtml", xhtml("写在前面", preface))
            archive.writestr(f"EPUB/{TOC_HREF}", xhtml("目录", toc_page))
            archive.writestr(f"EPUB/{NAV_HREF}", xhtml("目录", nav))
            archive.writestr(f"EPUB/{NCX_HREF}", ncx_document(toc_entries))
            archive.writestr("EPUB/book.opf", package_document(spine, list(images.values())))
        staged_epub.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="把 docs/ 下的求职系列文章合成 EPUB 3。")
    parser.add_argument("-o", "--output", type=Path, default=OUTPUT, help="输出路径，默认在仓库根目录")
    output = parser.parse_args().output.resolve()
    try:
        build_epub(output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"生成 EPUB 失败：{exc}\n")
    print(f"wrote {output} ({output.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()

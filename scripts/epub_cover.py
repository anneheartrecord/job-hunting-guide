"""用 Pillow 绘制 EPUB 的竖版封面。"""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from book_common import ENGLISH_TITLE, SUBTITLE, TITLE

FONT_FACES = (
    (("Hiragino Sans GB.ttc", 0), ("Hiragino Sans GB.ttc", 2)),
    (("NotoSansCJK-Regular.ttc", 2), ("NotoSansCJK-Bold.ttc", 2)),
    (("NotoSansCJKsc-Regular.otf", 0), ("NotoSansCJKsc-Bold.otf", 0)),
    (("msyh.ttc", 0), ("msyhbd.ttc", 0)),
)


def cover_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    for (regular_file, regular_index), (bold_file, bold_index) in FONT_FACES:
        try:
            regular = ImageFont.truetype(regular_file, index=regular_index)
            bold = ImageFont.truetype(bold_file, index=bold_index)
        except OSError:
            continue
        return regular, bold
    raise ValueError("找不到封面所需的中文字体。请安装 Noto Sans CJK SC 的常规和粗体字重后重试。")


def render_epub_cover(credits: tuple[str, ...]) -> bytes:
    regular, bold = cover_fonts()
    cover = Image.new("RGB", (1024, 1536), "white")
    draw = ImageDraw.Draw(cover)
    left, right = 132, 912
    blue, ink, slate = "#3b82f6", "#0f172a", "#475569"

    kicker_font = regular.font_variant(size=38)
    x = left
    for char in ENGLISH_TITLE:
        draw.text((x, 386), char, font=kicker_font, fill=blue, anchor="ls")
        x += kicker_font.getlength(char) + 9

    draw.text((left, 484), TITLE, font=bold.font_variant(size=158), fill=ink, anchor="lt")

    subtitle_font = regular.font_variant(size=55)
    first, separator, second = SUBTITLE.partition("：")
    draw.text((left, 706), first + separator, font=subtitle_font, fill=slate, anchor="lt")
    draw.text((left, 784), second, font=subtitle_font, fill=slate, anchor="lt")
    draw.rounded_rectangle((left, 933, left + 247, 955), radius=11, fill=blue)

    credit_size = 30
    credit_font = regular.font_variant(size=credit_size)
    longest = max(credit_font.getlength(line) for line in credits)
    if longest > right - left:
        credit_font = regular.font_variant(size=int(credit_size * (right - left) / longest))
    for row, line in enumerate(credits):
        draw.text((left, 1202 + row * 46), line, font=credit_font, fill=slate, anchor="lt")

    buffer = BytesIO()
    cover.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()

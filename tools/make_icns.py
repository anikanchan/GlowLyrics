# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Renders the GlowLyrics app icon.
    make_icns.py out.iconset   -> macOS .iconset folder (used by build_mac_app.sh)
    make_icns.py out.ico       -> Windows .ico file (used by build_windows_exe.bat)"""
import os
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter


def render(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    m = size * 0.09  # macOS icon grid margin
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, QColor("#ff3d7f"))
    g.setColorAt(1, QColor("#7a5cff"))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(r, r.width() * 0.225, r.width() * 0.225)
    f = QFont()
    f.setPixelSize(int(size * 0.55))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return img


def make_ico(out_path):
    import io
    from PIL import Image
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    render(256).save(buf, "PNG")
    img = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main(out_dir):
    QGuiApplication(sys.argv[:1])
    if out_dir.lower().endswith(".ico"):
        make_ico(out_dir)
        return
    os.makedirs(out_dir, exist_ok=True)
    for s in (16, 32, 128, 256, 512):
        render(s).save(os.path.join(out_dir, f"icon_{s}x{s}.png"))
        render(s * 2).save(os.path.join(out_dir, f"icon_{s}x{s}@2x.png"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "GlowLyrics.iconset")

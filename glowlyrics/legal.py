# Copyright © 2026 Tirhut LLC. All rights reserved.
"""License agreement (shown on first launch) and legal document viewer."""
import os
import re
import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from . import COPYRIGHT

# Change this when LICENSE.txt changes, so users are asked to accept the new terms.
LICENSE_VERSION = "2026-11-07"


def _candidates(name):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [os.path.join(here, name)]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(os.path.join(meipass, name))
        paths.append(os.path.join(os.path.dirname(meipass), "Resources", name))  # macOS .app
    paths.append(os.path.join(os.path.dirname(sys.executable), name))
    return paths


def read_doc(name):
    for p in _candidates(name):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return (f"{name} could not be found.\n\n{COPYRIGHT}\n"
            "GlowLyrics is provided \"AS IS\" without warranty of any kind.")


def reflow(text):
    """Join hard-wrapped lines into paragraphs so the text wraps nicely in a window."""
    heading = re.compile(r"^(\d+\.\s+)?[A-Z][A-Z0-9 ,&'\-/()]+:?$")
    out = []
    for para in text.split("\n\n"):
        merged = []
        for ln in para.split("\n"):
            st = ln.strip()
            if not merged:
                merged.append(ln)
                continue
            prev = merged[-1].strip()
            is_head = lambda x: len(x) < 40 and heading.match(x)
            new_item = (re.match(r"\(\w\)\s", st) or st.startswith(("-", "=", "Effective", "Copyright",
                                                                          "License", "Source"))
                        or is_head(st) or is_head(prev) or prev.startswith("=")
                        or prev.endswith(":"))
            if new_item:
                merged.append(ln)
            else:
                merged[-1] = merged[-1].rstrip() + " " + st
        out.append("\n".join(merged))
    return "\n\n".join(out)


def _text_box(text, wrap=True):
    box = QPlainTextEdit(reflow(text) if wrap else text)
    box.setReadOnly(True)
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSize(max(10, f.pointSize()))
    box.setFont(f)
    box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if wrap
                        else QPlainTextEdit.LineWrapMode.NoWrap)
    return box


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GlowLyrics — License Agreement")
        self.resize(680, 600)
        lay = QVBoxLayout(self)
        intro = QLabel("<b>Welcome to GlowLyrics.</b> Please read and accept the license agreement "
                       "to continue.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        lay.addWidget(_text_box(read_doc("LICENSE.txt")))
        self.agree = QCheckBox("I have read and agree to the GlowLyrics License Agreement")
        lay.addWidget(self.agree)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("Accept", QDialogButtonBox.ButtonRole.AcceptRole)
        decline = buttons.addButton("Decline and Quit", QDialogButtonBox.ButtonRole.RejectRole)
        self.ok.setEnabled(False)
        self.agree.toggled.connect(self.ok.setEnabled)
        self.ok.clicked.connect(self.accept)
        decline.clicked.connect(self.reject)
        lay.addWidget(buttons)
        foot = QLabel(COPYRIGHT)
        foot.setStyleSheet("color:gray;font-size:11px;")
        lay.addWidget(foot)


def ensure_accepted(cfg):
    """Returns True if the user has accepted the current license (asking if needed)."""
    if cfg["license_accepted"] == LICENSE_VERSION:
        return True
    dlg = LicenseDialog()
    dlg.raise_()
    dlg.activateWindow()
    if dlg.exec() == QDialog.DialogCode.Accepted:
        cfg.set("license_accepted", LICENSE_VERSION)
        cfg.save()
        return True
    return False


def show_document(parent, title, name):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(700, 600)
    lay = QVBoxLayout(dlg)
    lay.addWidget(_text_box(read_doc(name), wrap=(name != "THIRD-PARTY-LICENSES.txt")))
    close = QPushButton("Close")
    close.clicked.connect(dlg.accept)
    lay.addWidget(close)
    dlg.exec()

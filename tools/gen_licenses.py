# Copyright © 2026 Tirhut LLC. All rights reserved.
"""Collects the full license texts of every installed third-party package into one
file (THIRD-PARTY-LICENSES.txt). Run with the app's own virtualenv Python."""
import importlib.metadata as md
import os
import sys

SKIP = {"pip", "setuptools", "wheel", "pyinstaller", "pyinstaller-hooks-contrib",
        "altgraph", "macholib", "packaging", "pefile", "pywin32-ctypes"}
NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")


def main(out_path):
    dists = sorted(md.distributions(), key=lambda d: (d.metadata["Name"] or "").lower())
    parts = ["GLOWLYRICS - FULL THIRD-PARTY LICENSE TEXTS",
             "Copyright © 2026 Tirhut LLC. All rights reserved.",
             "Each package below is licensed under its own terms.", ""]
    seen = set()
    for d in dists:
        name = d.metadata["Name"] or "?"
        if name.lower() in SKIP or name.lower() in seen:
            continue
        seen.add(name.lower())
        lic = d.metadata.get("License-Expression") or d.metadata.get("License") or ""
        if len(lic) > 200:
            lic = lic.splitlines()[0]
        classifiers = [c.split("::")[-1].strip() for c in d.metadata.get_all("Classifier") or []
                       if c.startswith("License ::")]
        parts += ["=" * 79, f"{name} {d.version}",
                  f"License: {lic or ', '.join(classifiers) or 'see text below'}",
                  f"Home: {d.metadata.get('Home-page') or ''}", "=" * 79]
        texts = []
        for f in d.files or []:
            base = f.name.upper()
            if any(base.startswith(n) for n in NAMES) and ("dist-info" in str(f) or "licenses" in str(f).lower()):
                try:
                    texts.append(f"--- {f.name} ---\n" + f.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    pass
        parts.append("\n".join(texts) if texts else "(No license file shipped; see the License field above.)")
        parts.append("")
    if any(n in seen for n in ("pyside6", "pyside6-essentials", "shiboken6")):
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "licenses")
        for fname, title in (("LGPL-3.0.txt", "GNU LESSER GENERAL PUBLIC LICENSE v3 (applies to PySide6 / Qt)"),
                             ("GPL-3.0.txt", "GNU GENERAL PUBLIC LICENSE v3 (incorporated by reference in the LGPLv3)")):
            parts += ["=" * 79, title, "=" * 79]
            try:
                with open(os.path.join(here, fname), encoding="utf-8") as fh:
                    parts.append(fh.read())
            except OSError:
                parts.append("See https://www.gnu.org/licenses/")
            parts.append("")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"Wrote {out_path} ({len(seen)} packages)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "THIRD-PARTY-LICENSES.txt")

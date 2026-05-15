"""Progressive background pre-translation.

Scans game files for Japanese strings, then translates them in small batches
in a background thread. The user can start playing at any time — translations
are stored to the shared SQLite cache as they complete.
"""

import os
import re
import json
import logging
import threading
import time
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

HIRAGANA = range(0x3040, 0x30A0)
KATAKANA = range(0x30A0, 0x3100)

SCAN_EXTS = {".dll"}
SCAN_ONLY_PREFIXES = ["Assembly-CSharp", "Assembly"]  # Only scan game assemblies, not system DLLs
SKIP_NAMES = {"settings", "config", "license", "readme", "boot",
              "ScriptingAssemblies", "RuntimeInitializeOnLoads", "app"}
MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


def _decode_utf8_seq(data: bytes, pos: int) -> tuple[int, int] | None:
    if pos >= len(data):
        return None
    b = data[pos]
    if b == 0:
        return None
    if b < 0x80:
        return (b, pos + 1)
    if b < 0xC0:
        return None
    if b < 0xE0:
        if pos + 1 >= len(data):
            return None
        cp = ((b & 0x1F) << 6) | (data[pos + 1] & 0x3F)
        return (cp, pos + 2) if 0x80 <= cp <= 0x7FF else None
    if b < 0xF0:
        if pos + 2 >= len(data):
            return None
        cp = ((b & 0x0F) << 12) | ((data[pos + 1] & 0x3F) << 6) | (data[pos + 2] & 0x3F)
        if 0xD800 <= cp <= 0xDFFF:
            return None
        return (cp, pos + 3) if 0x800 <= cp <= 0xFFFF else None
    if b < 0xF8:
        if pos + 3 >= len(data):
            return None
        cp = ((b & 0x07) << 18) | ((data[pos + 1] & 0x3F) << 12) | ((data[pos + 2] & 0x3F) << 6) | (data[pos + 3] & 0x3F)
        return (cp, pos + 4) if 0x10000 <= cp <= 0x10FFFF else None
    return None


def _is_game_text(text: str) -> bool:
    if not text or len(text) < 2 or len(text) > 200:
        return False
    if not any(0x3040 <= ord(c) < 0x30A0 for c in text):
        return False
    if text.startswith(("Assets/", "http://", "https://", "0x", "//", "/*", "<", "{", "#")):
        return False
    if any(kw in text for kw in ("::", "__", ".dll", ".cs")):
        return False
    stripped = text.strip("。！？、 …\t\n\r「」『』（）()")
    if len(stripped) < 2 or stripped.isascii():
        return False
    return True


def _extract_from_file(filepath: str) -> set[str]:
    strings = set()
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except Exception:
        return strings
    pos = 0
    while pos < len(data):
        run_start = pos
        chars, has_kana = [], False
        run_pos = pos
        while run_pos < len(data) and len(chars) < 300:
            result = _decode_utf8_seq(data, run_pos)
            if result is None:
                break
            cp, next_pos = result
            if cp < 0x20 and cp not in (0x09, 0x0A, 0x0D):
                break
            if cp in HIRAGANA or cp in KATAKANA:
                has_kana = True
            try:
                chars.append(chr(cp))
            except ValueError:
                break
            run_pos = next_pos
        text = "".join(chars).strip()
        if has_kana and _is_game_text(text):
            strings.add(text)
        pos = max(run_start + 1, pos + 1)
    return strings


_scan_progress = {"file": "", "files_done": 0, "found": 0}


def scan_game_directory(game_path: str) -> set[str]:
    """Quick scan of a Unity game directory for Japanese strings."""
    global _scan_progress
    _scan_progress = {"file": "", "files_done": 0, "found": 0}

    all_strings = set()
    data_dir = None
    for item in os.listdir(game_path):
        if item.endswith("_Data") and os.path.isdir(os.path.join(game_path, item)):
            data_dir = os.path.join(game_path, item)
            break
    if not data_dir:
        return all_strings

    files_scanned = 0
    for root, dirs, files in os.walk(data_dir):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            name_lower = os.path.splitext(filename)[0].lower()
            if any(s in name_lower for s in SKIP_NAMES):
                continue
            if ext not in SCAN_EXTS:
                continue
            # Only scan game assemblies, skip system/framework DLLs
            if not any(filename.startswith(p) for p in SCAN_ONLY_PREFIXES):
                continue
            filepath = os.path.join(root, filename)
            try:
                if os.path.getsize(filepath) > MAX_FILE_SIZE:
                    continue
                _scan_progress["file"] = filename
                new = _extract_from_file(filepath)
                if new:
                    all_strings.update(new)
                files_scanned += 1
                _scan_progress["files_done"] = files_scanned
                _scan_progress["found"] = len(all_strings)
            except Exception:
                pass

    logger.info(f"Scan: {files_scanned} files → {len(all_strings)} unique Japanese strings")
    return all_strings


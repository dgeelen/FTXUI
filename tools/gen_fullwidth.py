#!/usr/bin/env python3
"""Regenerate g_full_width_characters in src/ftxui/screen/string.cpp.

The width-2 set is East_Asian_Width in {W, F} unioned with the default
emoji-presentation glyphs (Emoji_Presentation=Yes). Characters that become
wide only when followed by U+FE0F (VARIATION SELECTOR-16) - e.g. U+26A0,
U+2764 - are intentionally excluded: string_width() widens those via its
VS16 peek, not this table.

Usage:
    python3 tools/gen_fullwidth.py EastAsianWidth.txt emoji-data.txt

Download the two inputs (matching versions) from, e.g.:
    https://www.unicode.org/Public/UCD/latest/ucd/EastAsianWidth.txt
    https://www.unicode.org/Public/UCD/latest/ucd/emoji/emoji-data.txt

It prints a diff against the current table and refuses to emit if any range
would shrink (a glyph going from wide to narrow shifts existing layouts and
is almost always a parsing mistake, not a real Unicode change). On success it
rewrites the array in place.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STRING_CPP = REPO / "src" / "ftxui" / "screen" / "string.cpp"
FLOOR = 0x1100  # everything wide below this is already covered; keep ASCII/Latin narrow


def parse_props(path, want):
    cps = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2 or parts[1] not in want:
            continue
        rng = parts[0]
        lo, hi = (rng.split("..") + [rng])[:2] if ".." in rng else (rng, rng)
        cps.update(range(int(lo, 16), int(hi, 16) + 1))
    return cps


def to_intervals(cps):
    out = []
    for cp in sorted(cps):
        if out and cp == out[-1][1] + 1:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return [(a, b) for a, b in out]


def current_intervals(text):
    body = re.search(r"g_full_width_characters\s*=\s*\{\{(.*?)\}\}", text, re.S).group(1)
    return [(int(a, 16), int(b, 16))
            for a, b in re.findall(r"\{\s*0x([0-9a-fA-F]+)\s*,\s*0x([0-9a-fA-F]+)\s*\}", body)]


def fmt_intervals(cps):
    return ", ".join(f"U+{a:04X}" + (f"..U+{b:04X}" if b != a else "")
                     for a, b in to_intervals(set(cps)))


def render_array(intervals):
    lines = [f"constexpr std::array<Interval, {len(intervals)}> "
             "g_full_width_characters = {{"]
    line = "    "
    for a, b in intervals:
        cell = "{0x%05x, 0x%05x}," % (a, b)
        if len(line) + len(cell) + 1 > 76:
            lines.append(line.rstrip())
            line = "    "
        line += cell + " "
    if line.strip():
        lines.append(line.rstrip())
    lines.append("}};")
    return "\n".join(lines)


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    eaw = parse_props(argv[1], {"W", "F"})
    emoji = parse_props(argv[2], {"Emoji_Presentation"})
    wide = {c for c in (eaw | emoji) if c >= FLOOR}
    new_iv = to_intervals(wide)

    text = STRING_CPP.read_text(encoding="utf-8")
    cur = set()
    for a, b in current_intervals(text):
        cur.update(range(a, b + 1))

    added, removed = sorted(wide - cur), sorted(cur - wide)
    print(f"EAW W/F: {len(eaw)}  Emoji_Presentation: {len(emoji)}  union>=U+1100: {len(wide)}")
    print(f"intervals: {len(new_iv)}   added: {len(added)}   removed: {len(removed)}")
    if added:
        print("ADDED  :", fmt_intervals(added))
    if removed:
        print("REMOVED:", fmt_intervals(removed))
        print("\nRefusing to shrink existing ranges - inspect the inputs.", file=sys.stderr)
        return 1

    new_text = re.sub(r"constexpr std::array<Interval, \d+> g_full_width_characters = \{\{.*?\}\};",
                      render_array(new_iv), text, count=1, flags=re.S)
    STRING_CPP.write_text(new_text, encoding="utf-8")
    print(f"\nRewrote {STRING_CPP.relative_to(REPO)} ({len(new_iv)} intervals).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

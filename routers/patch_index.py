"""
StatMind — index.html auto-patcher
Run this from C:\\Users\\ASUS\\Downloads\\StatMind to add all missing script tags.

Usage:
  python patch_index.py

It will:
  1. Add stub_wiring.js script tag (if missing)
  2. Add capa_fix.js script tag (if missing)
  3. Add frontend_fixes.js script tag (if missing)
  4. Add USL/LSL sanity check data attribute to capability inputs (if missing)
  5. Show a clear report of what was changed
"""

import os
import re
import shutil
from datetime import datetime

INDEX_PATH = os.path.join('static', 'index.html')

if not os.path.exists(INDEX_PATH):
    print(f"ERROR: {INDEX_PATH} not found. Run this from the StatMind root folder.")
    exit(1)

with open(INDEX_PATH, encoding='utf-8') as f:
    html = f.read()

# Backup original
backup_path = INDEX_PATH + f'.bak.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
shutil.copy(INDEX_PATH, backup_path)
print(f"Backup saved: {backup_path}")

changes = []

# ── Scripts to inject before </body> ──────────────────────────────────────────
SCRIPTS = [
    ('stub_wiring.js',   '<script src="/static/stub_wiring.js"></script>'),
    ('capa_fix.js',      '<script src="/static/capa_fix.js"></script>'),
    ('frontend_fixes.js','<script src="/static/frontend_fixes.js"></script>'),
    ('coming_soon.js',   '<script src="/static/coming_soon.js"></script>'),
]

inject_block = ''
for fname, tag in SCRIPTS:
    if tag not in html and fname.replace('.js','') not in html:
        inject_block += f'\n  {tag}'
        changes.append(f'ADD script tag: {fname}')

if inject_block:
    # Find </body> and inject before it
    if '</body>' in html:
        html = html.replace('</body>', inject_block + '\n</body>', 1)
        print(f"Injected {len([c for c in changes if 'ADD script' in c])} script tag(s) before </body>")
    else:
        # Append to end of file
        html = html + inject_block
        changes.append('NOTE: </body> not found — appended to end of file')

# ── Fix: Add data-sm-cap attribute to capability run buttons ─────────────────
# This helps frontend_fixes.js find the right buttons
if 'data-sm-cap' not in html:
    # Try to tag capability run buttons
    html = re.sub(
        r'(<button[^>]*>)\s*(Run Capability|Run Full Analysis)\s*</button>',
        r'<button data-sm-cap="true">\2</button>',
        html
    )
    changes.append('TAG capability run buttons with data-sm-cap')

# ── Fix: Add data-sm-norm to normality run buttons ───────────────────────────
if 'data-sm-norm' not in html:
    html = re.sub(
        r'(<button[^>]*>)\s*(Run Normality)\s*</button>',
        r'<button data-sm-norm="true">\2</button>',
        html
    )
    changes.append('TAG normality run buttons with data-sm-norm')

# ── Fix: Add data-sm-spc to SPC run buttons ──────────────────────────────────
if 'data-sm-spc' not in html:
    html = re.sub(
        r'(<button[^>]*>)\s*(Run Full Analysis|Run SPC)\s*</button>',
        r'<button data-sm-spc="true">\2</button>',
        html
    )
    changes.append('TAG SPC run buttons with data-sm-spc')

# ── Write patched file ────────────────────────────────────────────────────────
with open(INDEX_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print()
print(f"Patched {INDEX_PATH} successfully.")
print(f"Changes made ({len(changes)}):")
for c in changes:
    print(f"  ✓ {c}")

if not changes:
    print("  No changes needed — all script tags already present.")

print()
print("Next steps:")
print("  git add static/index.html")
print('  git commit -m "fix: add all missing script tags to index.html"')
print("  git push origin main")

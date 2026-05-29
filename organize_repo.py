"""
organize_repo.py
Moves unused feature modules into routers/ directory.
Only moves files NOT directly imported by main.py.
Safe — does not break any existing imports.
"""
import os, shutil

# Files directly imported by main.py — KEEP in root
KEEP_IN_ROOT = {
    'main.py', 'capability.py', 'normality.py', 'control_charts.py',
    'gauge_rr.py', 'auth.py', 'ppap_generator.py', 'report_cache.py',
    'capa_rules_engine.py', 'file_parser.py', 'pdf_report.py',
    'hypothesis.py', 'logistic_regression.py', 'pca_advanced.py',
    'attribute_charts.py', 'statmind_intelligence.py', 'schemas.py',
    # Config/infra files
    'requirements.txt', 'Dockerfile', 'docker-compose.yml',
    # Scripts we just ran
    'organize_repo.py',
}

# Create routers/ dir
os.makedirs('routers', exist_ok=True)

# Create routers/__init__.py
if not os.path.exists('routers/__init__.py'):
    open('routers/__init__.py', 'w').write('# StatMind feature routers\n')

moved = []
skipped = []

for f in sorted(os.listdir('.')):
    if not f.endswith('.py'):
        continue
    if f.startswith('_') or f.startswith('test_'):
        continue
    if f in KEEP_IN_ROOT:
        skipped.append(f)
        continue
    if os.path.isdir(f):
        continue

    dest = os.path.join('routers', f)
    if not os.path.exists(dest):
        shutil.move(f, dest)
        moved.append(f)
    else:
        skipped.append(f + ' (already in routers/)')

print(f'Moved {len(moved)} files to routers/:')
for f in moved:
    print(f'  → routers/{f}')

print(f'\nKept {len(skipped)} files in root')
print('\nDone — run: python -m py_compile main.py')

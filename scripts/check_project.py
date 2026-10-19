from pathlib import Path

REQUIRED = [
    'app.py',
    'requirements.txt',
    'config/settings.py',
    'ui/layouts/user_layout.py',
    'ui/theme/theme_loader.py',
]
missing = [path for path in REQUIRED if not Path(path).exists()]
if missing:
    print('Missing files:')
    for path in missing:
        print(' -', path)
    raise SystemExit(1)
print('Project foundation check passed.')

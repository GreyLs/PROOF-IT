"""Disposable untrusted-document parser. No database, shared storage or .env access."""
from pathlib import Path
import json
import sys


def main():
    from .resource_limits import apply_limits
    apply_limits()
    directory, kind = Path(sys.argv[1]).resolve(), sys.argv[2]
    if kind == 'profile_export':
        from .export import export_profile
        profile = json.loads((directory / 'input.json').read_bytes())
        export_profile(profile, directory / 'result.pdf')
    elif kind in ('employment', 'employment_compare'):
        from .employment import extract_employment, compare_employment
        result=compare_employment(json.loads((directory/'input.json').read_bytes())) if kind=='employment_compare' else extract_employment(next(directory.glob('input.*')))
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    elif kind == 'qualification_generate':
        from .qualification import generate
        result=generate(json.loads((directory/'input.json').read_bytes()))
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    else:
        from .extraction import extract
        path = next(directory.glob('input.*'))
        result = extract(path, kind)
        payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
        if len(payload) > 4 * 1024**2:
            raise ValueError('Extracted document exceeds output limit')
        (directory / 'result.json').write_bytes(payload)


if __name__ == '__main__':
    main()

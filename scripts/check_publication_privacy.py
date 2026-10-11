"""Reject concrete temporary ingress URLs in publishable files; never print URLs."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = re.compile(r'https?://[a-z0-9-]+\.(?:trycloudflare\.com|serveo\.net|serveousercontent\.com|loca\.lt)', re.I)


def check():
    names = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT
    ).decode().split('\0')
    leaks = []
    for name in sorted(set(names)):
        path = ROOT / name
        if not name or not path.is_file():
            continue
        content = path.read_bytes().decode('utf-8', errors='ignore')
        if path.suffix.lower() == '.pdf':
            import pymupdf
            with pymupdf.open(path) as document:
                content += '\n'.join(page.get_text() + str(page.get_links()) for page in document)
                content += str(document.metadata)
        if ADDRESS.search(content):
            leaks.append(name)
    if leaks:
        raise RuntimeError('Private ingress address in publishable files: ' + ', '.join(leaks))
    print('Publication privacy check passed: no concrete ingress URLs in Git file set or PDFs.')


if __name__ == '__main__':
    check()

"""Machine-local ingress state, outside the checkout and source packages."""
import os
from pathlib import Path


def private_dir():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    directory = base / 'Proofit' / 'private-ingress'
    directory.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    if directory.resolve().is_relative_to(root):
        raise RuntimeError('Private ingress directory must be outside the repository')
    return directory


def private_file(name):
    if Path(name).name != name:
        raise ValueError('Expected a file name, not a path')
    return private_dir() / name

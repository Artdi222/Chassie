"""Install a Live2D model from a downloaded .zip or a picked folder into model/.

People download models as archives with extra things around the model: a PSD, a readme,
licence text, sometimes the whole package one or two folders deep. We find every folder
that holds a Cubism 3/4 ``*.model3.json`` and copy just that folder, skipping artwork
sources. Nothing outside the destination folder is ever written (no zip-slip)."""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILES = 5000
MAX_BYTES = 1536 * 1024 * 1024  # Uncompressed; textures for 4K models stay well under this.
SKIP_SUFFIXES = {'.psd', '.clip', '.cmo3', '.can3', '.zip', '.rar', '.7z'}
SKIP_PARTS = {'__MACOSX', '.DS_Store', 'Thumbs.db'}


class ImportError_(ValueError):
    """A problem the person can fix; the message is shown to them as is."""


def _clean(name):
    parts = PurePosixPath(name.replace('\\', '/')).parts
    if not parts or name.startswith('/') or any(p in ('..', '') for p in parts) or ':' in parts[0]:
        return None
    if any(p in SKIP_PARTS or p.startswith('._') for p in parts):
        return None
    return PurePosixPath(*parts)


def _slug(name):
    name = re.sub(r'[^\w.\- ]+', '', name, flags=re.UNICODE).strip(' .-')
    return re.sub(r'\s+', ' ', name)[:60] or 'Model'


def _plan(names):
    """Map each model package root to its files. names: iterable of PurePosixPath."""
    names = list(names)
    if any(n.name.endswith('.model.json') for n in names) and not any(n.name.endswith('.model3.json') for n in names):
        raise ImportError_('This is an older Cubism 2 model (.model.json). Chassie needs a Cubism 3 or 4 model '
                           'with a .model3.json file.')
    roots = sorted({n.parent for n in names if n.name.endswith('.model3.json')}, key=lambda p: len(p.parts))
    if not roots:
        raise ImportError_('No Live2D model found. Look for a .model3.json file: the zip or folder you pick '
                           'must contain it together with its .moc3 and textures.')
    packages = {}
    for root in roots:
        if any(root.is_relative_to(r) for r in packages):  # A model nested inside another is its asset.
            continue
        packages[root] = [n for n in names if n.is_relative_to(root) and n.suffix.lower() not in SKIP_SUFFIXES]
    return packages


def _target_name(root, model_dir, fallback):
    stem = root.name or _slug(fallback)
    base = _slug(stem)
    if base.lower() in ('model', 'models', 'runtime', 'live2d'):
        base = _slug(fallback) or base
    name, n = base, 2
    while (model_dir / name).exists():
        name, n = f'{base} {n}', n + 1
    return name


def install(source, model_dir, *, fallback_name='Model'):
    """source: a zip path, or a folder path whose files were uploaded. Returns new model ids."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    if fallback_name == 'Model':
        fallback_name = source.stem
    if source.is_dir():
        files = {}
        for path in source.rglob('*'):
            if path.is_file() and (clean := _clean(path.relative_to(source).as_posix())):
                files[clean] = path
        def read(name, out):
            with files[name].open('rb') as f: shutil.copyfileobj(f, out)
        sizes = {n: files[n].stat().st_size for n in files}
    else:
        try:
            archive = zipfile.ZipFile(source)
        except zipfile.BadZipFile:
            raise ImportError_('That file is not a zip archive. Unpack .rar or .7z files first, then pick the folder.')
        infos = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not info.flag_bits & 0x800:  # Not flagged UTF-8: Japanese zips are usually cp932.
                try:
                    name = name.encode('cp437').decode('cp932')
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            if clean := _clean(name):
                infos[clean] = info
        files = infos
        def read(name, out):
            with archive.open(infos[name]) as f: shutil.copyfileobj(f, out)
        sizes = {n: infos[n].file_size for n in infos}
    packages = _plan(files)
    chosen = [n for names in packages.values() for n in names]
    if len(chosen) > MAX_FILES:
        raise ImportError_(f'This model has more than {MAX_FILES} files, which is more than Chassie accepts.')
    if sum(sizes[n] for n in chosen) > MAX_BYTES:
        raise ImportError_('This model is larger than 1.5 GB unpacked, which is more than Chassie accepts.')
    installed = []
    for root, names in packages.items():
        target_name = _target_name(root, model_dir, fallback_name)
        staging = Path(tempfile.mkdtemp(prefix='.import-', dir=model_dir))
        try:
            for name in names:
                dest = (staging / name.relative_to(root)).resolve()
                if not dest.is_relative_to(staging.resolve()):
                    raise ImportError_('The archive contains an unsafe file path.')
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open('wb') as out:
                    read(name, out)
            staging.rename(model_dir / target_name)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        installed.append(target_name)
    return installed

"""Resumable ranged download for large pinned model artifacts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import fcntl
import os
import time
import urllib.request


def download(url,path,size,sha256,workers=8,block_size=16*1024*1024):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix(path.suffix+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        _download(url,path,size,sha256,workers,block_size)


def _download(url,path,size,sha256,workers,block_size):
    if path.is_file() and path.stat().st_size==size:
        with path.open('rb') as file:
            if hashlib.file_digest(file,'sha256').hexdigest()==sha256:return
    parts=path.with_suffix(path.suffix+'.parts');parts.mkdir(exist_ok=True)
    block=block_size
    def fetch(start):
        end=min(start+block,size)-1;part=parts/str(start)
        if part.exists() and part.stat().st_size>end-start+1:part.unlink()
        if part.is_file() and part.stat().st_size==end-start+1:return
        for attempt in range(4):
            offset=part.stat().st_size if part.exists() else 0
            if offset==end-start+1:return
            request=urllib.request.Request(url,headers={'Range':f'bytes={start+offset}-{end}'})
            try:
                with urllib.request.urlopen(request,timeout=120) as response:
                    if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start+offset}-{end}/{size}':raise ValueError('Server returned unexpected range')
                    with part.open('ab') as out:
                        remaining=end-start+1-offset
                        while remaining:
                            data=response.read(min(1024*1024,remaining))
                            if not data:raise IOError('Incomplete download')
                            out.write(data);remaining-=len(data)
                try:print(f'{path.parent.name}/{path.name}: chunk {start//block+1}/{(size+block-1)//block}',flush=True)
                except BrokenPipeError:pass  # A closed terminal must not invalidate downloaded bytes.
                return
            except Exception:
                if attempt==3:raise
                time.sleep(1+attempt)
    with ThreadPoolExecutor(max_workers=workers) as pool:list(pool.map(fetch,range(0,size,block)))
    pending=path.with_suffix(path.suffix+'.assembling');digest=hashlib.sha256()
    with pending.open('wb') as out:
        for start in range(0,size,block):
            with (parts/str(start)).open('rb') as file:
                while data:=file.read(1024*1024):out.write(data);digest.update(data)
    if pending.stat().st_size!=size or digest.hexdigest()!=sha256:
        pending.unlink(missing_ok=True)
        for start in range(0,size,block):(parts/str(start)).unlink(missing_ok=True)
        raise ValueError('Asset checksum mismatch; invalid partial data removed for retry')
    os.replace(pending,path)
    for start in range(0,size,block):(parts/str(start)).unlink()
    try:parts.rmdir()
    except OSError:pass  # Preserve any files not created by this downloader.

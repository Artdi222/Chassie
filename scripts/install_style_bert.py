"""Install a pinned, isolated Koharune Ami runtime; leave VOICEVOX untouched."""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
from download_speech_asset import download

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'.chassie/style-bert'
CPU_TORCH='torch-2.3.1+cpu-cp312-cp312-linux_x86_64.whl'
CPU_TORCH_URL='https://download.pytorch.org/whl/cpu/torch-2.3.1%2Bcpu-cp312-cp312-linux_x86_64.whl'
CPU_TORCH_SHA='2141a6cb7021adf2f92a0fd372cfeac524ba460bd39ce3a641d30a561e41f69a'
MODELS={
    'litagin/sbv2_koharune_ami':('7af50fba79c52110046679eb5a0c8895afc5c584',{
        'koharune-ami/config.json':'model/config.json',
        'koharune-ami/style_vectors.npy':'model/style_vectors.npy',
        'koharune-ami/koharune-ami.safetensors':'model/model.safetensors',
        'README.md':'MODEL_CARD.md'}),
    'ku-nlp/deberta-v2-large-japanese-char-wwm':('547b0e8b044fba3f9b84d0ab9f990440bd130c8b',{
        name:'bert/'+name for name in ['config.json','model.safetensors','special_tokens_map.json','tokenizer_config.json','vocab.txt']})}


def download_models():
    for repo,(revision,files) in MODELS.items():
        with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true',timeout=60) as r:
            metadata={p['rfilename']:p for p in json.load(r)['siblings']}
        for name,relative in files.items():
            path=DEST/relative;path.parent.mkdir(parents=True,exist_ok=True)
            info=metadata[name];expected=info.get('lfs',{}).get('sha256')
            if path.is_file() and path.stat().st_size==info['size']:
                with path.open('rb') as file:
                    if not expected or hashlib.file_digest(file,'sha256').hexdigest()==expected:continue
            if expected and info['size']>16*1024*1024:
                download(f'https://huggingface.co/{repo}/resolve/{revision}/{name}?download=true',path,info['size'],expected)
                continue
            pending=path.with_suffix(path.suffix+'.download')
            print('Downloading '+relative,flush=True)
            try:
                with urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}?download=true',timeout=300) as r,pending.open('wb') as out:
                    shutil.copyfileobj(r,out,1024*1024)
                if pending.stat().st_size!=info['size']:raise ValueError('Incomplete model download: '+relative)
                if expected:
                    with pending.open('rb') as f:
                        if hashlib.file_digest(f,'sha256').hexdigest()!=expected:raise ValueError('Model checksum mismatch')
                pending.replace(path)
            finally:pending.unlink(missing_ok=True)
    (DEST/'SOURCES.json').write_text(json.dumps({repo:{'revision':rev,'files':files} for repo,(rev,files) in MODELS.items()},indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--models-only',action='store_true')
    parser.add_argument('--device',choices=('cpu','cuda'),default='cpu');args=parser.parse_args()
    DEST.mkdir(parents=True,exist_ok=True)
    lock=(DEST/'install.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX)
    if not args.models_only:
        uv=shutil.which('uv')
        if not uv:raise RuntimeError('uv is required for the isolated speech environment')
        runtime=DEST/'cpu' if args.device=='cpu' else DEST
        runtime.mkdir(parents=True,exist_ok=True)
        python=runtime/'venv/bin/python'
        env={**os.environ,'UV_HTTP_TIMEOUT':'300','UV_CONCURRENT_DOWNLOADS':'8'}
        if args.device=='cpu' and (sys.version_info[:2]!=(3,12) or sys.platform!='linux' or os.uname().machine!='x86_64'):
            raise RuntimeError('The pinned CPU installer requires Linux x64 and Python 3.12.')
        if not python.exists():subprocess.run([uv,'venv','--cache-dir',str(DEST/'pip-cache'),'--python',sys.executable,str(runtime/'venv')],check=True,env=env)
        base=[uv,'pip','install','--python',str(python),'--cache-dir',str(DEST/'pip-cache')]
        if args.device=='cpu':
            wheel=DEST/'wheels'/CPU_TORCH
            download(CPU_TORCH_URL,wheel,190367618,CPU_TORCH_SHA,workers=16,block_size=4*1024*1024)
            torch=str(wheel)
            base.extend(['--find-links',str(DEST/'wheels')])
            for name in ('model','bert'):
                (DEST/name).mkdir(exist_ok=True)
                link=runtime/name
                if not link.exists() and not link.is_symlink():link.symlink_to('../'+name,target_is_directory=True)
        else:torch='torch==2.3.1'
        subprocess.run([*base,torch,'style-bert-vits2==2.5.0','transformers==4.44.2','numpy==1.26.4',
                        'accelerate==0.34.2','setuptools==80.9.0','pyopenjtalk-dict==0.3.4.dev2','scipy',
                        '--index-url','https://pypi.org/simple'],check=True,env=env)
    download_models()
    print(('Koharune Ami model files verified.' if args.models_only else 'Koharune Ami installed.')+' Voice source: あみたろの声素材工房 https://amitaro.net/',flush=True)

if __name__=='__main__':main()

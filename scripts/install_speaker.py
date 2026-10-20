"""Download the official WeSpeaker model for local speaker identification."""
from pathlib import Path
import hashlib
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
SHA256='5ef208a9da1453335308a6b6f4e6dfbd7e183a38b604de0a57664f45d257fe94'
URL='https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx'


def install():
    folder=ROOT/'.chassie'/'speaker-models';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'wespeaker_en_voxceleb_resnet34.onnx'
    if path.is_file():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=SHA256:raise RuntimeError('Speaker model checksum mismatch')
        return path
    pending=path.with_suffix('.download')
    try:
        with urllib.request.urlopen(URL,timeout=30) as response,pending.open('wb') as output:
            total=0
            while block:=response.read(1024*1024):
                total+=len(block)
                if total>30_000_000:raise RuntimeError('Unexpected speaker model size')
                output.write(block)
        if total!=26534365:raise RuntimeError('Incomplete speaker model')
        if hashlib.sha256(pending.read_bytes()).hexdigest()!=SHA256:raise RuntimeError('Speaker model checksum mismatch')
        pending.replace(path)
        (folder/'SOURCE.txt').write_text('WeSpeaker VoxCeleb ResNet34; CC BY 4.0.\n'
            'https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md#model-license\n'+URL+'\n'
            'Downloaded SHA256: '+hashlib.sha256(path.read_bytes()).hexdigest()+'\n')
        return path
    finally:pending.unlink(missing_ok=True)


if __name__=='__main__':print(install())

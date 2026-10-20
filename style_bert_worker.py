"""Isolated local Koharune Ami CUDA worker. Stdout is JSON lines, never logs."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time


def main():
    root=Path(sys.argv[1]);device=sys.argv[2];threads=int(sys.argv[3])
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',
                      HF_HOME=str(root/'hf-cache'),NUMBA_CACHE_DIR=str(root/'numba-cache'),
                      OPEN_JTALK_DICT_DIR=sys.argv[4])
    # Dependency startup messages must not corrupt the framed audio protocol.
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import torch
        from scipy.io import wavfile
        from style_bert_vits2.constants import Languages
        from style_bert_vits2.nlp import bert_models
        from style_bert_vits2.tts_model import TTSModel
        from style_bert_vits2.logging import logger
        logger.remove()
        import pyopenjtalk
        pyopenjtalk.run_frontend('こんにちは。')
        torch.set_num_threads(threads)
        if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA is unavailable')
        bert_models.load_model(Languages.JP,pretrained_model_name_or_path=str(root/'bert')).to(device)
        bert_models.load_tokenizer(Languages.JP,pretrained_model_name_or_path=root/'bert')
        model=TTSModel(model_path=root/'model/model.safetensors',config_path=root/'model/config.json',
                       style_vec_path=root/'model/style_vectors.npy',device=device)
        model.load()
        model.infer(text='こんにちは。',language=Languages.JP,style='Neutral',style_weight=.8)
    print(json.dumps({'ready':True,'styles':list(model.style2id),'device':device}),flush=True)
    while line:=sys.stdin.buffer.readline(8193):
        if len(line)>8192 or not line.endswith(b'\n'):raise ValueError('Request exceeds limit')
        request=json.loads(line);text=request['text'];style=request['style'];weight=request['weight']
        if not isinstance(text,str) or not 1<=len(text)<=350 or style not in model.style2id:raise ValueError('Invalid speech request')
        if type(weight) not in (int,float) or not .1<=weight<=1:raise ValueError('Invalid style strength')
        started=time.monotonic()
        with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():
            rate,audio=model.infer(text=text,language=Languages.JP,style=style,style_weight=weight,
                                   line_split=False,length=1.,sdp_ratio=.2)
        if len(audio)>rate*60 or not np.isfinite(audio).all():raise ValueError('Invalid generated audio')
        out=io.BytesIO();wavfile.write(out,rate,audio);data=out.getvalue()
        if not data or len(data)>8*1024*1024:raise ValueError('Audio exceeds limit')
        print(json.dumps({'wav':base64.b64encode(data).decode('ascii'),'seconds':time.monotonic()-started,
                          'duration':len(audio)/rate,'style':style}),flush=True)

if __name__=='__main__':main()

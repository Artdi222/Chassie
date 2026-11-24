"""Optional, bounded semantic recall from the existing Supabase index.

Cloud results must still exist in the current vault. A stale cloud row cannot
resurrect a deleted or edited note. Local search works without these services.
"""
import json
import math
from pathlib import Path
import re
import shlex
import threading
import time
import http.client
import socket
from urllib.parse import urlsplit


def env_file(path):
    result={}
    if not path or not Path(path).is_file(): return result
    for line in Path(path).read_text().splitlines():
        name,sep,value=line.partition('=')
        if sep and re.fullmatch(r'[A-Z_][A-Z_0-9]*',name.strip()):
            try: result[name.strip()]=' '.join(shlex.split(value,comments=True))
            except ValueError: continue
    return result


def request_json(url,key,payload,supabase=False,method=None):
    # Preserve the existing MCP server's IPv4-first behavior. TLS still validates
    # the original hostname, not the resolved address.
    target=urlsplit(url)
    if target.scheme not in ('http','https') or not target.hostname:
        raise ValueError('Invalid memory endpoint')
    connection_type=http.client.HTTPSConnection if target.scheme=='https' else http.client.HTTPConnection
    conn=connection_type(target.hostname,target.port,timeout=5)
    def ipv4_connection(address, timeout=5, source_address=None, **kwargs):
        addresses=socket.getaddrinfo(address[0],address[1],socket.AF_INET,socket.SOCK_STREAM)
        error=None
        for _,_,_,_,endpoint in addresses:
            try: return socket.create_connection(endpoint,timeout,source_address)
            except OSError as exc: error=exc
        raise error or OSError('No IPv4 address for memory endpoint')
    conn._create_connection=ipv4_connection
    headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
    if supabase: headers.update({'apikey':key,'Prefer':'return=representation'})
    try:
        conn.request(method or ('POST' if payload is not None else 'GET'),target.path+('?' + target.query if target.query else ''),body=json.dumps(payload).encode() if payload is not None else None,headers=headers)
        response=conn.getresponse()
        raw=response.read(2_000_001)
        if response.status>=400: raise RuntimeError('Memory service HTTP '+str(response.status))
        if len(raw)>2_000_000: raise ValueError('Remote memory response exceeded limit')
        return json.loads(raw) if raw else None
    finally: conn.close()


def validate_vector(result,config):
    vector=result['data'][0]['embedding']
    if len(vector)!=int(config.get('embedding_dimensions',2048)) or not all(type(v) in (int,float) and math.isfinite(v) for v in vector):
        raise ValueError('Embedding model dimensions do not match the index')
    return vector


class SemanticRecall:
    def __init__(self,config):
        self.config=config
        self._lock=threading.Lock(); self._worker=None
        self._cache={}; self.last_status='not_requested'

    def query(self,query,budget=.65):
        env=env_file(self.config.get('env_file',''))
        if not all(env.get(k) for k in ('SUPABASE_URL','SUPABASE_SERVICE_KEY','OPENROUTER_API_KEY','EMBEDDING_ENDPOINT','EMBEDDING_MODEL')):
            self.last_status='not_configured'; return []
        if env['EMBEDDING_MODEL']!=self.config.get('embedding_model'):
            self.last_status='embedding_model_mismatch'; return []
        with self._lock:
            cached=self._cache.get(query)
            if cached and time.monotonic()-cached[0]<60: return cached[1]
            if self._worker and self._worker.is_alive():
                self.last_status='busy_local_fallback'; return []
            def fetch():
                try:
                    result=request_json(env['EMBEDDING_ENDPOINT'],env['OPENROUTER_API_KEY'],{'model':env['EMBEDDING_MODEL'],'input':query[:2000]})
                    vector=validate_vector(result,self.config)
                    rows=request_json(env['SUPABASE_URL'].rstrip('/')+'/rest/v1/rpc/match_memories',env['SUPABASE_SERVICE_KEY'],{'query_embedding':vector,'match_threshold':.4,'match_count':8},True)
                    if not isinstance(rows,list): raise ValueError('Invalid memory rows')
                    with self._lock:
                        if len(self._cache)>=32: self._cache.pop(next(iter(self._cache)))
                        self._cache[query]=(time.monotonic(),rows)
                        self.last_status='okay'
                except Exception:
                    self.last_status='unavailable_local_fallback'
            self._worker=threading.Thread(target=fetch,daemon=True,name='chassie-semantic')
            worker=self._worker; worker.start()
        worker.join(max(0,min(budget,1.5)))
        with self._lock:
            cached=self._cache.get(query)
            if cached: return cached[1]
        self.last_status='timeout_local_fallback'
        return []


def validated_remote(store,rows):
    result=[]
    with store.db() as db:
        for remote in rows:
            source=remote.get('source_file')
            content=remote.get('content')
            if not isinstance(source,str) or not isinstance(content,str): continue
            # Match against already indexed, currently readable source text.
            body=re.sub(r'^\[File: .*?\]\s*','',content)
            normalized=' '.join(body.split())
            if len(normalized)<25: continue
            candidates=db.execute('SELECT * FROM chunks WHERE path=?',(source,)).fetchall()
            for row in candidates:
                live=' '.join(row['content'].split())
                if normalized in live or (len(live)>=100 and live in normalized):
                    item=dict(row); item['score']=float(remote.get('similarity',0)); result.append(item); break
    return result

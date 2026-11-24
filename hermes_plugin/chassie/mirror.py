"""Retryable pgvector mirror. Vault writes never depend on network success."""
import fcntl
import json
import threading
from urllib.parse import urlencode
from .remote import env_file, request_json


class CloudMirror:
    def __init__(self,store,config):
        self.store,self.config=store,config
        self.worker=None

    def kick(self):
        if not self.config.get('cloud_sync_enabled',False): return
        if self.worker and self.worker.is_alive(): return
        self.worker=threading.Thread(target=self.drain,daemon=True,name='chassie-cloud-mirror')
        self.worker.start()

    def drain(self,max_sources=100):
        # Multiple agents/processes share one mirror without overlapping replacements.
        with open(self.store.state/'cloud.lock','a') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return {'status':'busy'}
            env=env_file(self.config.get('env_file',''))
            if env.get('EMBEDDING_MODEL')!=self.config.get('embedding_model'):
                return {'status':'embedding_model_mismatch'}
            done=0
            for _ in range(max_sources):
                with self.store.db() as db:
                    job=db.execute('SELECT * FROM pending ORDER BY path LIMIT 1').fetchone()
                    if not job: return {'status':'okay','sources_synced':done}
                    chunks=[dict(r) for r in db.execute('SELECT * FROM chunks WHERE path=?',(job['path'],))]
                try:
                    self._sync_source(env,job['path'],chunks)
                except Exception:
                    return {'status':'unavailable_pending_retry','sources_synced':done}
                with self.store.db() as db:
                    db.execute('DELETE FROM pending WHERE path=? AND fingerprint=?',(job['path'],job['fingerprint']))
                done+=1
            return {'status':'pending','sources_synced':done}

    def _sync_source(self,env,path,chunks):
        base=env['SUPABASE_URL'].rstrip('/')+'/rest/v1/memories'
        query=urlencode({'source_file':'eq.'+path,'select':'id,content','limit':'1000'})
        old=request_json(base+'?'+query,env['SUPABASE_SERVICE_KEY'],None,True)
        if not isinstance(old,list) or len(old)>=1000: raise ValueError('Source needs a paginated maintenance pass')
        existing={r['content']:r['id'] for r in old}
        desired={c['content'] for c in chunks}
        inserts=[]
        for text in sorted(desired-set(existing)):
            response=request_json(env['EMBEDDING_ENDPOINT'],env['OPENROUTER_API_KEY'],{'model':env['EMBEDDING_MODEL'],'input':text})
            from .remote import validate_vector
            vector=validate_vector(response,self.config)
            inserts.append({'source_file':path,'content':text,'embedding':vector})
        # All replacement embeddings are ready before any remote row is removed.
        if inserts: request_json(base,env['SUPABASE_SERVICE_KEY'],inserts,True)
        # Keep one existing row per unchanged content and remove obsolete/duplicate IDs.
        seen=set(); remove=[]
        for row in old:
            if row['content'] not in desired or row['content'] in seen: remove.append(str(int(row['id'])))
            else: seen.add(row['content'])
        if remove:
            request_json(base+'?'+urlencode({'source_file':'eq.'+path,'id':'in.('+','.join(remove)+')'}),env['SUPABASE_SERVICE_KEY'],None,True,method='DELETE')

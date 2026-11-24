"""Vault-backed memory. SQLite is a rebuildable index, never the only copy."""
from __future__ import annotations
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

STOP = set('a an the is are was were i you my me we to of in on and or for it that this with do does did what which how about tell please aku saya kamu kita itu ini yang di ke dan atau untuk dari apa bagaimana tolong tentang punya'.split())
ALIASES = [('suka','kesukaan','like','love','prefer','preference','preferensi','favorit','favorite'), ('pakai','menggunakan','use','using'), ('kerja','work','job'), ('tinggal','live','address'), ('bahasa','language'), ('suara','voice','tts'), ('ingatan','memory','remember','ingat'), ('lahir','birthday','ulang','tahun'), ('ketemu','bertemu','pertemuan','meet','meeting','met'), ('pertama','first'), ('editor','editing','edit')]
UNCERTAIN = re.compile(r'\b(mungkin|seandainya|misalnya|contohnya|andaikan|kalau|jika|kayaknya|barangkali|maybe|perhaps|suppose|hypothetical|example|if|might|could|would)\b', re.I)
# Vault folder for memories Chassie saves (visible in Obsidian).
MANAGED_DIR = '_generated/chassie'
FACT = re.compile(r'\b(?:aku|saya|gue|gw|gua|i)\s+(?:(?:lebih|tidak|nggak|gak|ngga|don.t|do not|really|currently|sekarang)\s+)*(?:suka|prefer|like|love|hate|benci|pakai|menggunakan|use|work|kerja|bekerja|tinggal|live|seorang|lahir)\b|\b(?:namaku|nama saya|nama aku|my name is|my birthday is|ulang tahunku|aku lahir|saya lahir)\b', re.I)
SECRET = re.compile(r'\b(?:api[_ -]?key|password|passwd|token|secret|kata sandi|private key)\b|\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]+)',re.I)


# Saved memories mirror the vault taxonomy (_taxonomy.md): one readable note per fact.
CATEGORIES = {'people': 'People', 'events': 'Events', 'plans': 'Plans', 'technical': 'Technical',
              'learnings': 'Learnings', 'reflections': 'Reflections'}
INDEX_NOTE = 'Memories.md'  # Generated overview of MANAGED_DIR; never indexed itself.
OWNER_LINK = '[[Artdi]]'
_GUESS = [
    ('plans', re.compile(r'\b(?:akan|mau|ingin|berencana|rencana|besok|nanti|minggu depan|plan(?:s|ning)?|will|wants? to|going to|tomorrow|next week)\b', re.I)),
    ('events', re.compile(r'\b(?:\d{4}-\d{2}-\d{2}|hari ini|kemarin|tadi|lulus|ujian|ulang tahun|pertama kali|passed|today|yesterday|exam|birthday|first time)\b', re.I)),
    ('technical', re.compile(r'\b(?:kode|coding|aplikasi|program|config|model|server|github|python|app|code|bug|install)\b', re.I)),
    ('people', re.compile(r'\b(?:suka|tidak suka|benci|lebih suka|favorit|tinggal|sekolah|kerja|teman|keluarga|ibu|ayah|adik|kakak|pacar|prefer|likes?|loves?|hates?|lives?|works?|friend|family|mother|father|sister|brother)\b', re.I)),
]


def guess_category(text):
    return next((name for name, pattern in _GUESS if pattern.search(text)), 'people')


def guess_title(text):
    """Short heading from the fact itself: first clause, at most about eight words."""
    first = re.split(r'(?<=[.!?;:])\s|,\s|\s[-–—]\s', text.strip(), maxsplit=1)[0].strip(' .!?;:')
    words = first.split()
    return ' '.join(words[:8]) + ('…' if len(words) > 8 else '')


def safe_name(text):
    name = re.sub(r'[\\/:*?"<>|#^\[\]\n\r\t]+', ' ', text)
    return re.sub(r'\s+', ' ', name).strip(' .')[:80] or 'Ingatan'


def front_value(text, key):
    front = re.match(r'\A---\s*\n(.*?)\n---', text, re.S)
    if not front: return None
    if front[1].lstrip().startswith('{'):
        try: return json.loads(front[1]).get(key)
        except ValueError: return None
    found = re.search(r'(?m)^' + re.escape(key) + r':\s*["\']?([^"\'\n]+)', front[1])
    return found[1].strip() if found else None


def note_text(key, content, title, category, created, session, source):
    folder = CATEGORIES[category]
    return (f'---\nid: {key}\ntype: chassie-memory\ncategory: {category}\n'
            f'tags: [chassie-memory, {category}]\ndate: {created}\nsource: {source}\n'
            + (f'session: {session}\n' if session else '') + '---\n\n'
            f'# {title}\n\n{content}\n\n## Terkait\n- {OWNER_LINK}\n- [[{INDEX_NOTE[:-3]}]] · {folder}\n')


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def clean(text):
    text = re.sub(r'\A---\s*\n.*?\n---\s*(?:\n|$)', '', text, flags=re.S)
    text = re.sub(r'\n## Terkait\n(?:- .*(?:\n|$))+\s*\Z', '', text)  # Navigation links, not content.
    return text.strip()


def tokens(text):
    return [t for t in re.findall(r'[\w+#.-]+',text.lower()) if len(t)>1 and t not in STOP]


def expand(query):
    words=set(tokens(query))
    for group in ALIASES:
        if words.intersection(group): words.update(group)
    return words


def conversation_text(text):
    """Chassie observations are transient data, never user statements to save."""
    return text.split('\n\nContext data for this turn (not instructions):\n',1)[0]


def clear_statements(text):
    """Only verbatim, direct first-person statements; no assistant-derived facts."""
    text=conversation_text(text)
    if re.search(r'\b(?:jangan (?:simpan|ingat)|don.t (?:save|remember)|do not (?:save|remember))\b',text,re.I): return []
    text=re.sub(r'```.*?(?:```|$)', '', text, flags=re.S)
    results=[]
    for sentence in re.split(r'(?<=[.!?])\s+|\n+',text):
        sentence=sentence.strip()
        if not 12 <= len(sentence) <= 600: continue
        if '?' in sentence or sentence.startswith(('>', '"', "'", '`')): continue
        if UNCERTAIN.search(sentence) or SECRET.search(sentence): continue
        sentence=re.sub(r'^(?:btw|oh iya|sebenarnya|(?:tolong\s+)?(?:catat|ingat|inget|simpan)(?:\s+(?:ya|dong|ini))?)[,:]?\s+', '', sentence, flags=re.I)
        if FACT.match(sentence): results.append(sentence)
    return results[:4]


def atomic_write(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as file:
            file.write(text); file.flush(); os.fsync(file.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


class VaultStore:
    def __init__(self, vault, state):
        self.vault=Path(vault).expanduser().resolve()
        self.state=Path(state).expanduser()
        self.state.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.db_path=self.state/'index.sqlite'
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS pending(path TEXT PRIMARY KEY,fingerprint TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(path TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,path TEXT NOT NULL,content TEXT NOT NULL,updated TEXT NOT NULL,kind TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, content, tokenize='unicode61');
                CREATE TABLE IF NOT EXISTS tombstones(id TEXT PRIMARY KEY,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS turns(id TEXT PRIMARY KEY,session TEXT NOT NULL,created TEXT NOT NULL,statements TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS managed(id TEXT PRIMARY KEY,path TEXT NOT NULL);
            ''')
        os.chmod(self.db_path,0o600)

    @contextlib.contextmanager
    def db(self):
        db=sqlite3.connect(self.db_path,timeout=3)
        db.row_factory=sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextlib.contextmanager
    def lock(self):
        with open(self.state/'vault.lock','a') as file:
            fcntl.flock(file,fcntl.LOCK_EX)
            try: yield
            finally: fcntl.flock(file,fcntl.LOCK_UN)

    def _files(self):
        if not self.vault.is_dir(): raise FileNotFoundError('Configured memory vault is unavailable')
        found=[]
        for root, dirs, files in os.walk(self.vault,followlinks=False):
            dirs[:]=[d for d in dirs if not d.startswith('.') and d not in ('_daily','node_modules') and not (Path(root)/d).is_symlink()]
            for name in files:
                p=Path(root)/name
                if Path(root)==self.vault/MANAGED_DIR and name==INDEX_NOTE: continue
                if name.endswith('.md') and not name.startswith('.') and not p.is_symlink() and p.stat().st_size<=1_000_000:
                    found.append(p)
        return sorted(found)

    def refresh(self):
        """Read replacements completely before atomically replacing index rows."""
        managed_changed=False
        with self.lock(), self.db() as db:
            prior={r['path']:r['fingerprint'] for r in db.execute('SELECT * FROM sources')}
            current=set()
            for path in self._files():
                rel=path.relative_to(self.vault).as_posix(); current.add(rel)
                text=path.read_text(encoding='utf-8'); fingerprint=digest('index-v2\0'+text)
                if prior.get(rel)==fingerprint: continue
                content=clean(text)
                front=re.match(r'\A---\s*\n(.*?)\n---',text,re.S)
                note_date=None
                if front:
                    dated=re.search(r'(?m)^(?:date|created_at):\s*[\"\']?(\d{4}-\d{2}-\d{2})',front[1])
                    if dated: note_date=dated[1]
                if note_date: content='[Note date: '+note_date+']\n'+content
                kind='user_statement' if rel.startswith(MANAGED_DIR+'/') else 'vault_note'
                updated=dt.datetime.fromtimestamp(path.stat().st_mtime,dt.timezone.utc).isoformat()
                chunks=[]
                for index,start in enumerate(range(0,len(content),1400)):
                    part=content[start:start+1600].strip()
                    if len(part)>=12:
                        chunks.append((digest(rel+'\0'+str(index))[:24],rel,part,updated,kind))
                old=[r[0] for r in db.execute('SELECT id FROM chunks WHERE path=?',(rel,))]
                db.executemany('DELETE FROM search WHERE id=?',[(i,) for i in old])
                db.execute('DELETE FROM chunks WHERE path=?',(rel,))
                db.executemany('INSERT INTO chunks VALUES(?,?,?,?,?)',chunks)
                db.executemany('INSERT INTO search(id,content) VALUES(?,?)',[(c[0],c[2]) for c in chunks])
                if rel.startswith(MANAGED_DIR+'/'):
                    managed_changed=True
                    db.execute('DELETE FROM managed WHERE path=?',(rel,))
                    db.execute('INSERT OR REPLACE INTO managed VALUES(?,?)',(front_value(text,'id') or path.stem,rel))
                db.execute('INSERT OR REPLACE INTO sources VALUES(?,?)',(rel,fingerprint))
                db.execute('INSERT OR REPLACE INTO pending VALUES(?,?)',(rel,fingerprint))
            for rel in set(prior)-current:
                if rel.startswith(MANAGED_DIR+'/'):
                    managed_changed=True
                    row=db.execute('SELECT id FROM managed WHERE path=?',(rel,)).fetchone()
                    db.execute('INSERT OR IGNORE INTO tombstones VALUES(?,?)',(row['id'] if row else Path(rel).stem,dt.datetime.now(dt.timezone.utc).isoformat()))
                    db.execute('DELETE FROM managed WHERE path=?',(rel,))
                db.execute('DELETE FROM search WHERE id IN (SELECT id FROM chunks WHERE path=?)',(rel,))
                db.execute('DELETE FROM chunks WHERE path=?',(rel,))
                db.execute('DELETE FROM sources WHERE path=?',(rel,))
                db.execute('INSERT OR REPLACE INTO pending VALUES(?,?)',(rel,'deleted'))
        # Notes edited, renamed or deleted in Obsidian keep the overview current.
        if managed_changed and (self.vault/MANAGED_DIR).is_dir(): self.write_index()

    def search(self, query, limit=5):
        self.refresh()
        words=expand(query)
        if not words: return []
        expression=' OR '.join('"'+w.replace('"','""')+'"'+('*' if len(w)>=4 else '') for w in sorted(words)[:40])
        with self.db() as db:
            rows=db.execute('SELECT chunks.*,rank FROM search JOIN chunks ON chunks.id=search.id WHERE search MATCH ? ORDER BY rank LIMIT 40',(expression,)).fetchall()
        original=set(tokens(query)); ranked=[]
        for row in rows:
            item=dict(row); body=set(tokens(item['content']+' '+item['path']))
            overlap=len(original & body); expanded=len(words & body)
            # An event's own note should outrank long notes that merely mention
            # generic request words such as "reply", "source", or "memory".
            # Alias expansion applies to headings too (ketemu -> meeting).
            headings=' '.join(re.findall(r'(?m)^#{1,2}\s+(.+)$',item['content']))
            title=set(tokens(Path(item['path']).stem+' '+headings))
            title_hits=sum(bool(expand(word) & title) for word in original)
            item['score']=title_hits*12+overlap*3+expanded/max(1,len(words))
            item.pop('rank',None)
            ranked.append(item)
        ranked.sort(key=lambda r:(r['score'],r['updated']),reverse=True)
        seen=set(); result=[]
        for item in ranked:
            key=digest(re.sub(r'\s+',' ',item['content']).strip().lower())
            if key in seen: continue
            seen.add(key); result.append(item)
            if len(result)>=limit: break
        return result

    def list(self,limit=50,offset=0):
        self.refresh()
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM chunks ORDER BY updated DESC,id LIMIT ? OFFSET ?',(limit,offset))]

    def remember(self,content,*,session='',automatic=False,evidence=None,title=None,category=None):
        if not isinstance(content,str) or not 12<=len(content.strip())<=2000: raise ValueError('Memory content must be 12-2000 characters')
        content=content.strip()
        if SECRET.search(content): raise ValueError('Credentials are not stored as memory')
        if automatic and (content not in clear_statements(evidence or '') or content not in (evidence or '')):
            raise ValueError('Automatic memory requires an explicit verbatim user statement')
        category=category if category in CATEGORIES else guess_category(content)
        title=' '.join(str(title).split())[:80] if isinstance(title,str) and title.strip() else guess_title(content)
        key=digest(re.sub(r'\s+',' ',content).lower())[:24]
        now=dt.datetime.now(dt.timezone.utc)
        with self.lock(),self.db() as db:
            if db.execute('SELECT 1 FROM tombstones WHERE id=?',(key,)).fetchone():
                if automatic: return {'id':key,'saved':False,'reason':'previously_forgotten'}
                db.execute('DELETE FROM tombstones WHERE id=?',(key,))
            if self._find(key,db): return {'id':key,'saved':False,'reason':'duplicate'}
            folder=self.vault/MANAGED_DIR/CATEGORIES[category]
            base=f"{now.astimezone().date().isoformat()} {safe_name(title)}"
            path=folder/f'{base}.md'
            for n in range(2,100):
                if not path.exists(): break
                path=folder/f'{base} ({n}).md'
            if not path.resolve().is_relative_to(self.vault) or path.is_symlink():
                raise ValueError('Managed memory path must stay inside the vault')
            atomic_write(path,note_text(key,content,title,category,now.astimezone().date().isoformat(),session,
                                        'direct_user' if automatic else 'memory_tool'))
        self.refresh()
        return {'id':key,'saved':True,'source_file':path.relative_to(self.vault).as_posix()}

    def _find(self,key,db=None):
        """Path of the managed note with this id, from the index or (old layout) its file name."""
        legacy=self.vault/MANAGED_DIR/f'{key}.md'
        if legacy.is_file(): return legacy
        if db is None:
            with self.db() as conn: row=conn.execute('SELECT path FROM managed WHERE id=?',(key,)).fetchone()
        else: row=db.execute('SELECT path FROM managed WHERE id=?',(key,)).fetchone()
        if row and (self.vault/row['path']).is_file(): return self.vault/row['path']
        return None

    def write_index(self):
        """Regenerate Memories.md: every saved memory, grouped like the vault taxonomy."""
        root=self.vault/MANAGED_DIR
        groups={}
        for path in sorted(root.rglob('*.md')):
            if path.parent==root and path.name==INDEX_NOTE: continue
            text=path.read_text(encoding='utf-8')
            category=front_value(text,'category') or 'people'
            heading=re.search(r'(?m)^# (.+)$',text)
            created=front_value(text,'date') or ''
            groups.setdefault(CATEGORIES.get(category,'People'),[]).append((created,path.stem,heading[1] if heading else path.stem))
        lines=['---','tags: [index, chassie-memory]',f'updated: {dt.date.today().isoformat()}','---','',
               '# Ingatan Chassie','','Hal-hal yang Chassie simpan sendiri dari obrolan, dikelompokkan per kategori. '
               'Catatan ini dibuat otomatis; ubah atau hapus catatan aslinya, bukan daftar ini.','']
        for folder in CATEGORIES.values():
            items=groups.get(folder)
            if not items: continue
            lines+=[f'## {folder}','']
            lines+=[f'- {created} · [[{stem}|{heading}]]' for created,stem,heading in sorted(items,reverse=True)]
            lines.append('')
        atomic_write(root/INDEX_NOTE,'\n'.join(lines))

    def capture(self,user_content,session):
        self.refresh()
        statements=clear_statements(user_content)
        key=digest(session+'\0'+user_content)
        # Durable minimal evidence; never store full tool output or assistant replies.
        with self.db() as db:
            prior=db.execute('SELECT 1 FROM turns WHERE id=?',(key,)).fetchone()
        if prior: return []
        results=[self.remember(s,session=session,automatic=True,evidence=user_content) for s in statements]
        if statements:
            with self.db() as db:
                db.execute('INSERT OR IGNORE INTO turns VALUES(?,?,?,?)',(key,session,dt.datetime.now(dt.timezone.utc).isoformat(),'[]'))
        return results

    def _managed_path(self, identifier):
        if not re.fullmatch(r'[a-f0-9]{24}',str(identifier)): raise ValueError('Use a memory ID returned by search or list')
        self.refresh()
        found=self._find(identifier)
        if found: return found
        with self.db() as db:
            row=db.execute('SELECT path FROM chunks WHERE id=?',(identifier,)).fetchone()
        if row and row['path'].startswith(MANAGED_DIR+'/'):
            candidate=self.vault/row['path']
            if candidate.is_file() and candidate.resolve().is_relative_to((self.vault/MANAGED_DIR).resolve()): return candidate
        raise ValueError('This is a source vault note. Edit that note in Obsidian; only managed facts can be changed with this tool.')

    def forget(self,identifier):
        p=self._managed_path(identifier)
        with self.lock():
            key=front_value(p.read_text(encoding='utf-8'),'id') or p.stem
            with self.db() as db:
                db.execute('INSERT OR REPLACE INTO tombstones VALUES(?,?)',(key,dt.datetime.now(dt.timezone.utc).isoformat()))
            p.unlink()
        self.refresh()
        return {'deleted':True,'id':key}

    def update(self,identifier,content,session=''):
        if not isinstance(content,str) or not 12<=len(content.strip())<=2000 or SECRET.search(content):
            raise ValueError('Provide a non-secret memory of 12-2000 characters')
        # New fact is durable before the old fact is removed.
        p=self._managed_path(identifier)
        old=p.read_text(encoding='utf-8')
        if digest(re.sub(r'\s+',' ',content.strip()).lower())[:24]==(front_value(old,'id') or p.stem):
            return {'updated':False,'reason':'unchanged'}
        result=self.remember(content,session=session,category=front_value(old,'category'))
        self.forget(identifier)
        return {**result,'updated':True}

    def status(self):
        self.refresh()
        with self.db() as db:
            return {'vault_available':True,'sources':db.execute('SELECT count(*) FROM sources').fetchone()[0],
                    'chunks':db.execute('SELECT count(*) FROM chunks').fetchone()[0],
                    'pending_cloud_sources':db.execute('SELECT count(*) FROM pending').fetchone()[0],
                    'automatic_capture':'explicit_first_person_statements_only','remote_required':False}

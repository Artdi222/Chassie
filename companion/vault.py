"""Use the same vault/index as Hermes, without a second memory database."""
import importlib.util
import json
import sqlite3
from pathlib import Path


class VaultMemory:
    def __init__(self,home=None):
        self.home=Path(home or Path.home()/'.hermes').expanduser()
        self.store=None;self.error=None;self.path=None
        try:
            config=json.loads((self.home/'femiris.json').read_text())
            self.path=Path(config['vault_path']).expanduser()
            if not self.path.is_dir():raise ValueError('Obsidian vault is unavailable')
            source=self.home/'plugins/femiris/store.py'
            spec=importlib.util.spec_from_file_location('chassie_vault_store',source)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.store=module.VaultStore(self.path,self.home/'femiris-state')
        except (OSError,ValueError,KeyError,ImportError,sqlite3.Error) as exc:
            self.error=f'Vault unavailable ({type(exc).__name__}). Check the Chassie memory plugin in Hermes.'

    def require(self):
        if self.store is None:raise ValueError(self.error or 'Vault unavailable')
        return self.store

    def status(self):
        if self.store is None:return {'available':False,'error':self.error}
        try:return {'available':True,'path':str(self.path),**self.store.status()}
        except (OSError,sqlite3.Error):return {'available':False,'error':'Vault is temporarily unavailable. Try again shortly.'}

    def call(self,method,*args,**kwargs):
        try:return getattr(self.require(),method)(*args,**kwargs)
        except (OSError,sqlite3.Error) as exc:raise ValueError('Vault operation could not finish. Check the vault and try again.') from exc

    def list(self):
        return [{'id':row['id'],'content':row['content'],'source':row['path'],
                 'editable':row['path'].startswith('_generated/chassie/')} for row in self.call('list',100)]

    def add(self,text):return self.call('remember',text,session='chassie-memory-panel')
    def update(self,identifier,text):return self.call('update',identifier,text,'chassie-memory-panel')
    def delete(self,identifier):return self.call('forget',identifier)

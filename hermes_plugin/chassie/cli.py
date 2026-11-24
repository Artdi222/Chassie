"""Maintenance commands discovered by Hermes only when Chassie is active."""
import json

def run(args):
    from plugins.memory import load_memory_provider
    from hermes_constants import get_hermes_home
    provider=load_memory_provider('chassie',register_skills=False)
    if provider is None or not provider.is_available():
        raise SystemExit('Chassie is not configured. Check chassie.json and vault_path.')
    provider.initialize('maintenance',hermes_home=str(get_hermes_home()),platform='cli')
    operation=getattr(args,'chassie_operation','status')
    if operation=='sync':
        provider.store.refresh()
        result=provider.mirror.drain()
    elif operation=='search': result=provider.store.search(args.query)
    else: result=provider.store.status()
    print(json.dumps(result,ensure_ascii=False,indent=2))

def register_cli(subparser):
    subs=subparser.add_subparsers(dest='chassie_operation')
    subs.add_parser('status',help='Show local index and pending cloud synchronization')
    subs.add_parser('reindex',help='Refresh the local index from the vault')
    subs.add_parser('sync',help='Retry pending cloud mirror updates')
    search=subs.add_parser('search',help='Search saved vault evidence')
    search.add_argument('query')
    subparser.set_defaults(func=run)

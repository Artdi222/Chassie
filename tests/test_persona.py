import pytest
import yaml
from brain.config import save_local


def save_local_persona(text, root):
    save_local('companion', {'persona': text}, root)
from test_orchestrator import app  # noqa: F401


def test_persona_rewrites_only_its_key(tmp_path):
    local = tmp_path / 'config.local.yaml'
    local.write_text('# mine\nhermes:\n  provider: "anthropic"  # keep\ncompanion:\n  persona: >-\n    Old text\n    over lines.\n  guest_privacy: true\ntts:\n  translation_language: "id"\n')
    save_local_persona('New "quoted" persona: 100%', tmp_path)
    text = local.read_text()
    assert '# mine' in text and '# keep' in text
    data = yaml.safe_load(text)
    assert data == {'hermes': {'provider': 'anthropic'}, 'companion': {'persona': 'New "quoted" persona: 100%', 'guest_privacy': True},
                    'tts': {'translation_language': 'id'}}


def test_persona_added_when_missing(tmp_path):
    save_local_persona('Calm.', tmp_path)
    assert yaml.safe_load((tmp_path / 'config.local.yaml').read_text()) == {'companion': {'persona': 'Calm.'}}
    (tmp_path / 'config.local.yaml').write_text('companion:\n  guest_privacy: false\n')
    save_local_persona('Bright.', tmp_path)
    assert yaml.safe_load((tmp_path / 'config.local.yaml').read_text()) == {'companion': {'guest_privacy': False, 'persona': 'Bright.'}}


@pytest.mark.asyncio
async def test_set_persona_control(app, tmp_path):
    app._local_config_root = tmp_path
    await app.handle_control({'type': 'set_persona', 'persona': '  Shy\n but kind. '})
    assert app._settings()['persona'] == 'Shy\n but kind.'
    assert app._hermes._persona == 'Shy but kind.'
    assert yaml.safe_load((tmp_path / 'config.local.yaml').read_text())['companion']['persona'] == 'Shy\n but kind.'
    await app.handle_control({'type': 'set_persona', 'persona': '  '})
    assert app._hermes._persona == '' and app._settings()['persona'] == ''  # Empty: SOUL.md alone.
    for bad in ('x' * 4001, 5):
        with pytest.raises(ValueError): await app.handle_control({'type': 'set_persona', 'persona': bad})

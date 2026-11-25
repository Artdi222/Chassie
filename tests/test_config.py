from brain.config import load_config, merge


def test_local_overrides_merge_into_defaults(tmp_path):
    (tmp_path / 'config.yaml').write_text('stt:\n  language: null\n  model: small\ntts:\n  translation_language: en\n')
    assert load_config(tmp_path)['stt'] == {'language': None, 'model': 'small'}
    (tmp_path / 'config.local.yaml').write_text('stt:\n  language: id\n')
    config = load_config(tmp_path)
    assert config['stt'] == {'language': 'id', 'model': 'small'} and config['tts']['translation_language'] == 'en'


def test_merge_replaces_non_dict_values():
    assert merge({'a': {'b': 1, 'c': [1]}}, {'a': {'c': [2]}, 'd': 3}) == {'a': {'b': 1, 'c': [2]}, 'd': 3}


def test_repo_defaults_are_english_and_impersonal():
    from pathlib import Path
    import yaml
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / 'config.yaml').read_text())
    assert config['tts']['translation_language'] == 'en' and config['stt']['language'] is None
    assert config['hermes']['personal_memory_profile_id'] is None

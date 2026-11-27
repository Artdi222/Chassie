import json
from brain import hermes_catalog as catalog

AUTH = '''anthropic (1 credentials):
  #1  claude_code          oauth   id=d45440 priority=0 claude_code ←

custom:9router (1 credentials):
  #1  9router              api_key id=09314f priority=0 config:9router ←

nous (1 credentials):
  #1  someone@example.com oauth   id=ba925d priority=0 device_code ←

openai-api (1 credentials):
  #1  OPENAI_API_KEY       api_key id=cbdf29 priority=0 env:OPENAI_API_KEY ←
'''


def home(tmp_path):
    (tmp_path / 'models_dev_cache.json').write_text(json.dumps({
        'anthropic': {'name': 'Anthropic', 'env': ['ANTHROPIC_API_KEY'], 'models': {
            'claude-haiku-5-5': {'name': 'Claude Haiku 5.5', 'reasoning': True, 'modalities': {'input': ['text', 'image']}}}},
        'openai': {'name': 'OpenAI', 'env': ['OPENAI_API_KEY'], 'models': {
            'gpt-text': {'name': 'GPT Text', 'reasoning': False, 'modalities': {'input': ['text']}}}},
        'deepseek': {'name': 'DeepSeek', 'env': ['DEEPSEEK_API_KEY'], 'models': {}}}))
    (tmp_path / 'cache').mkdir()
    (tmp_path / 'cache/model_catalog.json').write_text(json.dumps({'providers': {
        'nous': {'metadata': {'display_name': 'Nous Portal'}, 'models': [{'id': 'hermes-4'}]}}}))
    return tmp_path


def test_providers_signed_in_first_and_never_the_account(tmp_path):
    providers = catalog.providers(home(tmp_path), auth_output=AUTH)
    assert [p['id'] for p in providers[:4]] == ['anthropic', 'custom:9router', 'nous', 'openai-api']
    assert all(p['signed_in'] for p in providers[:4]) and not any(p['signed_in'] for p in providers[4:])
    assert {'id': 'deepseek', 'label': 'DeepSeek', 'signed_in': False, 'key_name': 'DEEPSEEK_API_KEY'} in providers
    assert 'example.com' not in json.dumps(providers)
    assert next(p for p in providers if p['id'] == 'openai-api')['label'] == 'OpenAI'  # Hermes id, models.dev data.


def test_models_with_vision_and_reasoning(tmp_path):
    root = home(tmp_path)
    assert catalog.models(root, 'anthropic') == [{'id': 'claude-haiku-5-5', 'name': 'Claude Haiku 5.5', 'vision': True, 'reasoning': True}]
    assert catalog.models(root, 'openai-api')[0]['vision'] is False
    assert catalog.models(root, 'nous') == [{'id': 'hermes-4', 'name': 'hermes-4', 'vision': None, 'reasoning': None}]
    assert catalog.models(root, 'custom:9router') == []  # Typed by hand.
    assert catalog.key_name(root, 'deepseek') == 'DEEPSEEK_API_KEY' and catalog.key_name(root, 'nous') is None

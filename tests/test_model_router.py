import json
from pathlib import Path

import pytest
from backend.app import model_router as router


def test_preferences_default_and_atomic_save(tmp_path, monkeypatch):
    target = tmp_path / 'prefs.json'
    monkeypatch.setenv('RAG_MODEL_PREFERENCES_FILE', str(target))
    assert router.get_preferences() == {'mode': 'AUTO', 'model': ''}
    assert router.save_preferences('MANUAL', 'qwen2.5:1.5b') == {'mode': 'MANUAL', 'model': 'qwen2.5:1.5b'}
    assert json.loads(target.read_text())['model'] == 'qwen2.5:1.5b'
    assert router.save_preferences('AUTO') == {'mode': 'AUTO', 'model': ''}


def test_invalid_preferences_rejected():
    with pytest.raises(ValueError): router.save_preferences('OTHER')
    with pytest.raises(ValueError): router.save_preferences('MANUAL', '')


def test_manual_selection_requires_installed_model(tmp_path, monkeypatch):
    monkeypatch.setenv('RAG_MODEL_PREFERENCES_FILE', str(tmp_path / 'prefs.json'))
    router.save_preferences('MANUAL', 'llama3.2:1b')
    with pytest.raises(ValueError, match='no longer installed'):
        router.choose_model([{'name': 'qwen2.5:1.5b'}], [{'content': 'hello'}], 'qwen2.5:3b')
    selected, info = router.choose_model([{'name': 'llama3.2:1b'}], [{'content': 'hello'}], 'qwen2.5:3b')
    assert selected == 'llama3.2:1b' and info['mode'] == 'MANUAL'


def test_auto_uses_complexity_and_safe_models(tmp_path, monkeypatch):
    monkeypatch.setenv('RAG_MODEL_PREFERENCES_FILE', str(tmp_path / 'prefs.json'))
    monkeypatch.setattr(router, 'available_memory_gb', lambda: 8.0)
    models = [
        {'name': 'tiny:1b', 'details': {'parameter_size': '1B'}},
        {'name': 'mid:3b', 'details': {'parameter_size': '3B'}},
        {'name': 'large:7b', 'details': {'parameter_size': '7B'}},
    ]
    low, low_info = router.choose_model(models, [{'content': 'hello there'}], 'qwen2.5:3b')
    high, high_info = router.choose_model(models, [{'content': 'Explain architecture and root cause security impact'}], 'qwen2.5:3b')
    assert low == 'tiny:1b'
    assert high == 'mid:3b'  # conservative 55% of available memory budget
    assert low_info['complexity'] == 'low'
    assert high_info['complexity'] == 'high'

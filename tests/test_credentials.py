import os

import pytest

from regression_lab.credentials import load_key_file


def test_explicit_private_key_file(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    file = tmp_path/'.env.local'
    file.write_text('OPENAI_API_KEY=local-test-not-a-real-credential\n')
    file.chmod(0o600)
    load_key_file(file)
    assert os.environ['OPENAI_API_KEY'] == 'local-test-not-a-real-credential'


@pytest.mark.parametrize('contents,mode', [
    ('OPENAI_API_KEY=private-test-value\n', 0o644),
    ('OPENAI_API_KEY=private-test-value\nOTHER=bad\n', 0o600),
    ('OPENAI_API_KEY=$(private-test-value)\n', 0o600),
    ('OPENAI_API_KEY=\n', 0o600),
])
def test_unsafe_config_rejected_without_echoing_input(tmp_path, monkeypatch, contents, mode):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    file = tmp_path/'.env.local'
    file.write_text(contents)
    file.chmod(mode)
    with pytest.raises(ValueError) as err:
        load_key_file(file)
    assert 'private-test-value' not in str(err.value)
    assert 'OPENAI_API_KEY' not in os.environ


def test_symbolic_link_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    target = tmp_path/'target'
    target.write_text('OPENAI_API_KEY=local-test-value\n')
    target.chmod(0o600)
    link = tmp_path/'link'
    link.symlink_to(target)
    with pytest.raises(OSError):
        load_key_file(link)


def test_conflicting_environment_is_not_silently_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'environment-test-value')
    file = tmp_path/'.env.local'
    file.write_text('OPENAI_API_KEY=file-test-value\n')
    file.chmod(0o600)
    with pytest.raises(ValueError, match='disagree'):
        load_key_file(file)
    assert os.environ['OPENAI_API_KEY'] == 'environment-test-value'

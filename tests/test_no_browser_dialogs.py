"""No browser alert()/confirm()/prompt() anywhere in EdgeCase's own UI.

Standing UI rule: the app uses its own modals (showMessage / confirmDialog
in web/static/js/shared_utils.js). About sixty alert() calls had crept in;
this sweep keeps them out.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / 'web'
CALL = re.compile(r'(?<![\w.$])(alert|confirm|prompt)\s*\(')


def _sources():
    for path in sorted((WEB / 'static' / 'js').glob('*.js')):
        if not path.name.endswith('.min.js'):
            yield path
    yield from sorted((WEB / 'templates').rglob('*.html'))


def _code(text):
    text = re.sub(r'\{#.*?#\}', '', text, flags=re.S)        # Jinja comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)        # block comments
    return '\n'.join(line for line in text.splitlines()
                     if not line.lstrip().startswith('//'))


def test_no_browser_dialog_calls():
    found = []
    for path in _sources():
        for number, line in enumerate(_code(path.read_text()).splitlines(), 1):
            if CALL.search(line):
                found.append(f"{path.relative_to(WEB)}: {line.strip()[:90]}")
    assert not found, "browser dialogs:\n" + "\n".join(found)


def test_shared_dialog_helpers_exist_and_use_text_nodes():
    source = (WEB / 'static' / 'js' / 'shared_utils.js').read_text()
    for name in ('function showMessage(', 'function confirmDialog(',
                 'function confirmSubmit('):
        assert name in source
    dialog = source[source.index('function _appDialog('):]
    assert 'innerHTML' not in dialog

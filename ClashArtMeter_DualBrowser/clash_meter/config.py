"""Per-user, local-only application settings."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

APP_NAME = 'ClashArtMeter'
DATA_DIR = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.local' / 'share')) / APP_NAME
CONFIG_FILE = DATA_DIR / 'settings.json'
DB_FILE = DATA_DIR / 'history.sqlite3'
DEFAULTS = {
    'controller': 'http://127.0.0.1:9097',
    'secret': '',
    'mode': 'dual_gpt',
    'schema_version': 2,
    'keywords': 'chatgpt.com, openai.com, oaiusercontent.com, oaistatic.com',
    'always_on_top': True,
    'position': None,
    'collapsed': False,
}


def validate_controller(raw: str) -> str:
    """Only allow loopback controllers; never connect to remote admin APIs."""
    url = raw.strip().rstrip('/')
    parts = urlsplit(url)
    if (parts.scheme != 'http' or parts.hostname not in {'localhost', '127.0.0.1', '::1'}
            or parts.username or parts.password or parts.path or parts.query or parts.fragment):
        raise ValueError('控制器必须是本机 HTTP 地址，例如 http://127.0.0.1:9097')
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError('控制器端口不正确') from exc
    if port is None or not (1 <= port <= 65535):
        raise ValueError('请填写有效的控制器端口')
    return url


def load_config() -> dict:
    result = DEFAULTS.copy()
    saved = {}
    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        if isinstance(saved, dict):
            result.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, ValueError, TypeError):
        pass
    try:
        result['controller'] = validate_controller(str(result['controller']))
    except (ValueError, TypeError):
        result['controller'] = DEFAULTS['controller']
    if result['mode'] not in {'global', 'domains', 'process', 'dual_gpt'}:
        result['mode'] = 'dual_gpt'
    # On first upgrade, opt into the dual-ChatGPT mode while preserving the
    # previously saved API endpoint, Secret and window position.
    if isinstance(saved, dict) and saved and saved.get('schema_version') != 2:
        result['mode'] = 'dual_gpt'
        result['schema_version'] = 2
    if not isinstance(result['keywords'], str):
        result['keywords'] = DEFAULTS['keywords']
    if not isinstance(result['secret'], str):
        result['secret'] = ''
    return result


def save_config(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean = {key: data.get(key, default) for key, default in DEFAULTS.items()}
    clean['controller'] = validate_controller(str(clean['controller']))
    tmp = CONFIG_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(CONFIG_FILE)

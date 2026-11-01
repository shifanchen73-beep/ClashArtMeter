"""Conservative accounting of local Clash/Mihomo connection snapshots.

No browser instrumentation is performed. In dual_gpt mode, host matching detects
OpenAI-domain traffic and process metadata *may* attribute it to Edge/Chrome.
Unattributable bytes always remain in an explicit 'unknown' category.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PureWindowsPath
from typing import Any

MODES = {'global', 'domains', 'process', 'dual_gpt'}
DEFAULT_GPT_DOMAINS = 'chatgpt.com, openai.com, oaiusercontent.com, oaistatic.com'
BUCKETS = ('edge', 'chrome', 'unknown')
GAP_SECONDS = 5.0


def parse_keywords(raw: str) -> list[str]:
    return [part.strip().lower() for part in raw.replace('\n', ',').replace('，', ',').split(',') if part.strip()]


def bytes_label(size: float) -> str:
    size = max(0, size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.2f} {unit}'
        size /= 1024
    return '0 B'


def positive_increment(previous: Any, current: Any) -> int:
    try:
        a, b = int(previous), int(current)
        return max(0, b - a) if a >= 0 and b >= 0 else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def safe_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (ValueError, TypeError, OverflowError):
        return 0


def timestamp_epoch(iso_date: Any) -> float | None:
    if not isinstance(iso_date, str) or not iso_date:
        return None
    try:
        parsed = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc).timestamp() if parsed.tzinfo is None else parsed.timestamp()
    except ValueError:
        return None


def _hostname(connection: dict) -> str:
    metadata = connection.get('metadata') or {}
    if not isinstance(metadata, dict):
        return ''
    # Prefer sniffed hostname if host is only an IP; IP-only connections cannot
    # safely be attributed to a website without reverse-DNS guesswork.
    host = str(metadata.get('host') or '')
    sniff = str(metadata.get('sniffHost') or '')
    if not host or (host and host.replace('.', '').isdigit()):
        host = sniff or host
    host = host.lower().strip().rstrip('.')
    if host.count(':') == 1 and host.rsplit(':', 1)[1].isdigit():
        host = host.rsplit(':', 1)[0]
    return host


def domain_matches(connection: dict, keywords: list[str]) -> bool:
    host = _hostname(connection)
    return bool(host and any(host == item.lstrip('.') or host.endswith('.' + item.lstrip('.'))
                             for item in keywords))


def browser_from_connection(connection: dict, browser_ports: dict[int, str] | None = None) -> str:
    """Only attribute when the API explicitly provides an executable identity."""
    meta = connection.get('metadata') or {}
    if not isinstance(meta, dict):
        return 'unknown'
    # process='msedge.exe' / processPath='C:\\...\\msedge.exe' are supported.
    values = [str(meta.get(k) or '') for k in ('process', 'processName', 'processPath')]
    for value in values:
        # PureWindowsPath works for both slash conventions, independent of OS.
        name = PureWindowsPath(value.replace('/', '\\')).name.lower()
        if name in {'msedge.exe', 'msedge'}:
            return 'edge'
        if name in {'chrome.exe', 'chrome'}:
            return 'chrome'
    # Classic Clash often omits processPath. For a local HTTP/SOCKS proxy,
    # Windows can independently map the client's source TCP port to its PID.
    if browser_ports and str(meta.get('sourceIP') or '') in {'127.0.0.1', '::1'}:
        try:
            port = int(meta.get('sourcePort'))
        except (ValueError, TypeError):
            port = -1
        return browser_ports.get(port, 'unknown')
    return 'unknown'


def matches(connection: dict, mode: str, keywords: list[str]) -> bool:
    if mode == 'global':
        return True
    if mode in {'domains', 'dual_gpt'}:
        return domain_matches(connection, keywords)
    if mode == 'process':
        meta = connection.get('metadata') or {}
        if not isinstance(meta, dict):
            return False
        proc = ' '.join(str(meta.get(k) or '').lower()
                        for k in ('process', 'processName', 'processPath'))
        return bool(keywords and any(word in proc for word in keywords))
    return False


class TrafficAccumulator:
    """Accumulates per-second deltas and explicitly tracks attribution gaps.

    A connection absent from consecutive snapshots may never be seen. We do not
    manufacture bytes for such traffic. Pauses and reconnects reset baselines.
    """

    def __init__(self) -> None:
        self.active = False
        self.mode = 'dual_gpt'
        self.keywords: list[str] = parse_keywords(DEFAULT_GPT_DOMAINS)
        self.session_started: float | None = None
        self.session_up = 0
        self.session_down = 0
        self.last_global: tuple[int, int] | None = None
        self.last_connections: dict[str, tuple[int, int, str]] = {}
        self.last_wall: float | None = None
        self.last_mono: float | None = None
        self.up_speed = 0.0
        self.down_speed = 0.0
        self.total_up = 0
        self.total_down = 0
        self.last_breakdown: dict[str, tuple[int, int]] = {key: (0, 0) for key in BUCKETS}
        self.session_by_bucket: dict[str, tuple[int, int]] = {key: (0, 0) for key in BUCKETS}
        self.speed_by_bucket: dict[str, tuple[float, float]] = {key: (0.0, 0.0) for key in BUCKETS}
        self.matching_connections = 0
        self.attributed_connections = 0

    def start(self, mode: str, keywords: str, wall_time: float) -> None:
        if self.active:
            raise RuntimeError('已经开始统计')
        if mode not in MODES:
            raise ValueError('不支持的统计模式')
        self.active = True
        self.mode = mode
        self.keywords = parse_keywords(keywords)
        self.session_started = wall_time
        self.session_up = 0
        self.session_down = 0
        self.session_by_bucket = {key: (0, 0) for key in BUCKETS}
        self.last_breakdown = {key: (0, 0) for key in BUCKETS}

    def stop(self) -> None:
        self.active = False
        self.session_started = None

    def reset_baseline(self) -> None:
        self.last_global = None
        self.last_connections.clear()
        self.last_mono = None
        self.last_wall = None
        self.up_speed = 0.0
        self.down_speed = 0.0
        self.last_breakdown = {key: (0, 0) for key in BUCKETS}
        self.speed_by_bucket = {key: (0.0, 0.0) for key in BUCKETS}
        self.matching_connections = 0
        self.attributed_connections = 0

    def ingest(self, payload: dict, wall_time: float, monotonic_time: float,
               browser_ports: dict[int, str] | None = None) -> tuple[int, int]:
        if not isinstance(payload, dict):
            raise ValueError('Clash 返回数据不是对象')
        if 'uploadTotal' not in payload or 'downloadTotal' not in payload:
            raise ValueError('连接数据缺少 uploadTotal 或 downloadTotal')
        now_global = (safe_int(payload['uploadTotal']), safe_int(payload['downloadTotal']))
        items = payload.get('connections', [])
        if not isinstance(items, list):
            items = []
        now_conns: dict[str, tuple[int, int, str]] = {}
        for conn in items:
            if isinstance(conn, dict) and isinstance(conn.get('id'), str):
                now_conns[conn['id']] = (safe_int(conn.get('upload')),
                                          safe_int(conn.get('download')),
                                          str(conn.get('start') or ''))

        elapsed = monotonic_time - self.last_mono if self.last_mono is not None else 0.0
        valid = self.last_global is not None and 0 < elapsed <= GAP_SECONDS
        global_up = positive_increment(self.last_global[0], now_global[0]) if valid else 0
        global_down = positive_increment(self.last_global[1], now_global[1]) if valid else 0
        prev_conns = self.last_connections
        prev_wall = self.last_wall
        self.last_global = now_global
        self.last_connections = now_conns
        self.last_wall = wall_time
        self.last_mono = monotonic_time
        self.total_up, self.total_down = now_global

        tracking_mode = self.mode
        # Network speeds must be calculated from *matching* connections, never
        # displayed as filtered when they originate from global counters.
        tick = {key: [0, 0] for key in BUCKETS}
        filtered_up = filtered_down = 0
        matched = identified = 0
        if valid:
            for conn in items:
                if not isinstance(conn, dict) or not matches(conn, tracking_mode, self.keywords):
                    continue
                cid = conn.get('id')
                if not isinstance(cid, str):
                    continue
                matched += 1
                bucket = browser_from_connection(conn, browser_ports) if tracking_mode == 'dual_gpt' else 'unknown'
                if bucket != 'unknown':
                    identified += 1
                cur = now_conns.get(cid)
                if cur is None:
                    continue
                old = prev_conns.get(cid)
                if old is not None and old[2] == cur[2]:
                    inc_up = positive_increment(old[0], cur[0])
                    inc_down = positive_increment(old[1], cur[1])
                else:
                    started = timestamp_epoch(conn.get('start'))
                    # Credit fresh connections opened since the last successful
                    # sample; never count an old connection's whole lifetime.
                    can_credit = (started is not None and prev_wall is not None
                                  and started >= prev_wall - 0.3
                                  and started <= wall_time + 1)
                    if self.active and self.session_started is not None:
                        can_credit = can_credit and started >= self.session_started - 0.3
                    inc_up, inc_down = (cur[0], cur[1]) if can_credit else (0, 0)
                tick[bucket][0] += inc_up
                tick[bucket][1] += inc_down
                filtered_up += inc_up
                filtered_down += inc_down
        self.matching_connections = matched
        self.attributed_connections = identified
        if tracking_mode == 'global':
            speed_up, speed_down = global_up, global_down
        else:
            speed_up, speed_down = filtered_up, filtered_down
        self.up_speed = speed_up / elapsed if valid else 0
        self.down_speed = speed_down / elapsed if valid else 0
        self.speed_by_bucket = {
            key: (values[0] / elapsed if valid else 0, values[1] / elapsed if valid else 0)
            for key, values in tick.items()
        }
        self.last_breakdown = {key: tuple(values) for key, values in tick.items()}
        if not self.active or not valid:
            return 0, 0
        delta_up, delta_down = ((global_up, global_down) if self.mode == 'global'
                                else (filtered_up, filtered_down))
        self.session_up += delta_up
        self.session_down += delta_down
        if self.mode == 'dual_gpt':
            for key, (up, down) in self.last_breakdown.items():
                old_up, old_down = self.session_by_bucket[key]
                self.session_by_bucket[key] = (old_up + up, old_down + down)
        return delta_up, delta_down

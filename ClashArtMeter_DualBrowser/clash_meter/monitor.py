"""Poll the local Mihomo/Clash controller in a background thread."""
from __future__ import annotations

import json
import queue
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .config import validate_controller
from .winports import browser_ports


class LocalController:
    def __init__(self, base_url: str, secret: str):
        self.base_url = validate_controller(base_url)
        self.secret = secret
        # Never let system HTTP_PROXY settings proxy the local controller request.
        self.opener = build_opener(ProxyHandler({}))

    def fetch(self) -> dict:
        headers = {'Accept': 'application/json'}
        if self.secret:
            headers['Authorization'] = f'Bearer {self.secret}'
        request = Request(self.base_url + '/connections', headers=headers)
        try:
            with self.opener.open(request, timeout=1.8) as response:
                raw = response.read(5_000_000)
            return json.loads(raw)
        except HTTPError as err:
            if err.code in {401, 403}:
                raise ConnectionError('认证失败：请检查 API Secret') from err
            raise ConnectionError(f'HTTP {err.code}：检查控制器地址') from err
        except (URLError, TimeoutError, OSError) as err:
            raise ConnectionError('无法连接 Clash API：检查端口、运行状态和防火墙') from err
        except (UnicodeError, json.JSONDecodeError, ValueError) as err:
            raise ConnectionError('API 返回的数据无法解析') from err


class PollWorker:
    def __init__(self, controller: LocalController, outbox: queue.Queue):
        self.controller = controller
        self.outbox = outbox
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name='clash-poller', daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stopped.set()

    def _run(self) -> None:
        while not self.stopped.is_set():
            t0 = time.monotonic()
            try:
                data = self.controller.fetch()
                msg = ('sample', (data, browser_ports()), time.time(), time.monotonic())
            except (ConnectionError, ValueError) as error:
                msg = ('error', str(error), time.time(), time.monotonic())
            self.outbox.put(msg)
            self.stopped.wait(max(0.05, 1.0 - (time.monotonic() - t0)))

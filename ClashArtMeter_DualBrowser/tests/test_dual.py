"""Coverage for dual browser accounting, fallback and v1 DB upgrades."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from clash_meter import config
from clash_meter.core import TrafficAccumulator, browser_from_connection, domain_matches
from clash_meter.storage import SessionStore
from clash_meter.winports import browser_ports


def conn(cid, host, process='', up=0, down=0, start='1970-01-01T00:00:10.4Z',
         source_ip='127.0.0.1', source_port=31242):
    return {'id': cid, 'start': start, 'upload': up, 'download': down,
            'metadata': {'host': host, 'processPath': process,
                         'sourceIP': source_ip, 'sourcePort': source_port}}


def packet(conns, up=10_000, down=20_000):
    return {'connections': conns, 'uploadTotal': up, 'downloadTotal': down}


class DualTests(unittest.TestCase):
    def test_two_browsers_and_unattributed_are_not_double_counted(self):
        meter = TrafficAccumulator()
        meter.ingest(packet([]), 10, 10)
        meter.start('dual_gpt', 'chatgpt.com, openai.com', 10)
        cs = [conn('edge', 'chatgpt.com', r'C:\Program Files\Edge\msedge.exe', 50, 150),
              conn('chrome', 'chatgpt.com', r'C:\Chrome\chrome.exe', 60, 160),
              conn('unknown', 'api.openai.com', '', 70, 170),
              conn('foreign', 'www.tiktok.com', 'chrome.exe', 1000, 2000)]
        self.assertEqual(meter.ingest(packet(cs, 15000, 25000), 11, 11), (180, 480))
        self.assertEqual(meter.session_by_bucket['edge'], (50, 150))
        self.assertEqual(meter.session_by_bucket['chrome'], (60, 160))
        self.assertEqual(meter.session_by_bucket['unknown'], (70, 170))
        self.assertEqual((meter.up_speed, meter.down_speed), (180, 480))
        cs2 = [{**c, 'upload': c['upload']+10, 'download': c['download']+30} for c in cs]
        self.assertEqual(meter.ingest(packet(cs2, 16000, 26000), 12, 12), (30, 90))
        self.assertEqual(meter.session_up, 210)
        self.assertEqual(meter.session_down, 570)
        self.assertEqual(meter.session_by_bucket['chrome'], (70, 190))
        self.assertEqual(meter.session_by_bucket['unknown'], (80, 200))

    def test_windows_port_ownership_fallback_is_strictly_loopback(self):
        sample = conn('x', 'chatgpt.com', source_port='43456')
        self.assertEqual(browser_from_connection(sample, {43456: 'edge'}), 'edge')
        sample['metadata']['sourceIP'] = '192.168.100.3'
        self.assertEqual(browser_from_connection(sample, {43456: 'chrome'}), 'unknown')
        self.assertEqual(browser_from_connection(sample, {}), 'unknown')
        sample['metadata']['process'] = 'msedge.exe'
        self.assertEqual(browser_from_connection(sample, {43456: 'chrome'}), 'edge')
        self.assertEqual(browser_ports(), {}) if __import__('sys').platform != 'win32' else None

    def test_hostname_strict_matching(self):
        domains = ['openai.com', 'chatgpt.com']
        self.assertTrue(domain_matches(conn('1', 'foo.chatgpt.com'), domains))
        self.assertFalse(domain_matches(conn('2', 'evil-chatgpt.com'), domains))
        self.assertFalse(domain_matches(conn('3', 'chatgpt.com.example.org'), domains))
        self.assertTrue(domain_matches(conn('4', 'chatgpt.com:443'), domains))
        empty = conn('5', '')
        empty['metadata']['sniffHost'] = 'chatgpt.com'
        self.assertTrue(domain_matches(empty, domains))

    def test_filtered_speed_not_global_speed(self):
        meter = TrafficAccumulator()
        old = conn('x', 'chatgpt.com', 'chrome.exe', 100, 100,
                   start='1970-01-01T00:00:01Z')
        meter.ingest(packet([old], 1000, 2000), 10, 10)
        meter.start('domains', 'chatgpt.com', 10)
        updated = {**old, 'upload': 140, 'download': 180}
        self.assertEqual(meter.ingest(packet([updated], 4000, 9000), 11, 11), (40, 80))
        self.assertEqual((meter.up_speed, meter.down_speed), (40, 80))

    def test_counter_gap_disallows_fabricated_bytes(self):
        meter = TrafficAccumulator()
        meter.ingest(packet([]), 10, 10)
        meter.start('dual_gpt', 'chatgpt.com', 10)
        self.assertEqual(meter.ingest(packet([conn('x', 'chatgpt.com', 'chrome.exe', 10, 30)],
                                             10100, 20500), 20, 20), (0, 0))

    def test_store_migrates_v1_without_losing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'history.db'
            db = sqlite3.connect(path)
            db.execute('''CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
                ended_at TEXT, mode TEXT NOT NULL, keywords TEXT NOT NULL,
                upload_bytes INTEGER NOT NULL DEFAULT 0, download_bytes INTEGER NOT NULL DEFAULT 0)''')
            db.execute('INSERT INTO sessions(started_at,ended_at,mode,keywords,upload_bytes,download_bytes) '
                       'VALUES (?,?,?,?,?,?)', ('2026-01-01', '2026-01-01', 'global', '', 100, 200))
            db.commit()
            db.close()
            store = SessionStore(path)
            self.assertEqual(store.totals(), (1, 100, 200))
            sid = store.begin('dual_gpt', 'chatgpt.com')
            store.add(sid, 8, 12, {'edge': (4, 6), 'chrome': (2, 4), 'unknown': (2, 2)})
            store.finish(sid)
            rows = store.recent()
            self.assertEqual(rows[0][3:11], (8, 12, 4, 6, 2, 4, 2, 2))
            self.assertEqual(rows[1][3:5], (100, 200))
            store.close()

    def test_upgrade_keeps_existing_api_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            path.write_text(json.dumps({'controller': 'http://127.0.0.1:12345',
                                        'secret': 'private-value', 'mode': 'global'}))
            with patch.object(config, 'CONFIG_FILE', path):
                result = config.load_config()
            self.assertEqual(result['mode'], 'dual_gpt')
            self.assertEqual(result['controller'], 'http://127.0.0.1:12345')
            self.assertEqual(result['secret'], 'private-value')


if __name__ == '__main__':
    unittest.main()

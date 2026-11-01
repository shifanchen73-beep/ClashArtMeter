import unittest

from clash_meter.config import validate_controller
from clash_meter.core import TrafficAccumulator, bytes_label, matches, parse_keywords


def sample(up, down, conns=None):
    return {'uploadTotal': up, 'downloadTotal': down, 'connections': conns or []}


class CounterTests(unittest.TestCase):
    def test_session_excludes_baseline_and_idle(self):
        m = TrafficAccumulator()
        self.assertEqual(m.ingest(sample(100, 500), 10, 10), (0, 0))
        m.ingest(sample(200, 800), 11, 11)
        m.start('global', '', 11.2)
        self.assertEqual(m.ingest(sample(260, 1050), 12, 12), (60, 250))
        self.assertEqual((m.session_up, m.session_down), (60, 250))
        m.stop()
        self.assertEqual(m.ingest(sample(300, 1200), 13, 13), (0, 0))

    def test_counter_reset_and_connection_gap(self):
        m = TrafficAccumulator()
        m.ingest(sample(1000, 2000), 10, 10)
        m.start('global', '', 10)
        self.assertEqual(m.ingest(sample(10, 40), 11, 11), (0, 0))
        self.assertEqual(m.ingest(sample(20, 60), 12, 12), (10, 20))
        self.assertEqual(m.ingest(sample(100, 400), 50, 50), (0, 0))

    def test_filtered_old_and_new_connections(self):
        m = TrafficAccumulator()
        old = {'id': 'old', 'metadata': {'host': 'chatgpt.com'},
               'start': '1970-01-01T00:00:01Z', 'upload': 300, 'download': 500}
        m.ingest(sample(300, 500, [old]), 10, 10)
        m.start('domains', 'chatgpt.com,openai.com', 10)
        old2 = {**old, 'upload': 350, 'download': 700}
        fresh = {'id': 'new', 'metadata': {'host': 'images.openai.com'},
                 'start': '1970-01-01T00:00:10.6Z', 'upload': 30, 'download': 80}
        foreign = {'id': 'foreign', 'metadata': {'host': 'example.org'},
                   'start': '1970-01-01T00:00:10.5Z', 'upload': 200, 'download': 800}
        self.assertEqual(m.ingest(sample(580, 2080, [old2, fresh, foreign]), 11, 11), (80, 280))
        self.assertEqual(m.ingest(sample(600, 2100, []), 12, 12), (0, 0))

    def test_no_substring_domain_injection(self):
        good = {'metadata': {'host': 'a.chatgpt.com'}}
        bad = {'metadata': {'host': 'evilchatgpt.com'}}
        self.assertTrue(matches(good, 'domains', ['chatgpt.com']))
        self.assertFalse(matches(bad, 'domains', ['chatgpt.com']))
        self.assertTrue(matches({'metadata': {'processPath': 'C:/Chrome/chrome.exe'}},
                                'process', ['chrome']))

    def test_no_remote_controllers(self):
        self.assertEqual(validate_controller('http://127.0.0.1:9097'), 'http://127.0.0.1:9097')
        for url in ['http://0.0.0.0:9090', 'http://evil.test:9090',
                    'https://127.0.0.1:9090', 'http://127.0.0.1:9090/evil',
                    'http://127.0.0.1:abc']:
            with self.assertRaises(ValueError):
                validate_controller(url)

    def test_formatting(self):
        self.assertEqual(bytes_label(1024*1024), '1.00 MB')
        self.assertEqual(parse_keywords('openai.com, chatgpt.com\nabc.com'),
                         ['openai.com', 'chatgpt.com', 'abc.com'])


if __name__ == '__main__':
    unittest.main()

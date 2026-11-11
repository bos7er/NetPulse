import unittest
from unittest.mock import patch, Mock

from netpulse.network import calc_rates, format_rate, parse_ping_latency, probe, validate_host


class NetworkTests(unittest.TestCase):
    def test_host_validation(self):
        for name in ("1.1.1.1", "google.com", "::1", "example.local", "sub.example.com"):
            self.assertEqual(validate_host(name), name)
        for name in ("", "-n", "foo;del C:", "foo..com", "bad name", "-evil.com", "a" * 255):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_host(name)

    def test_ping_parse(self):
        self.assertEqual(parse_ping_latency("Reply time=12ms"), 12.0)
        self.assertEqual(parse_ping_latency("Czas=13ms"), 13.0)
        self.assertEqual(parse_ping_latency("czas<1ms"), 0.5)
        self.assertEqual(parse_ping_latency("time=10.7 ms"), 10.7)
        self.assertEqual(parse_ping_latency("czas=10,4 ms"), 10.4)
        self.assertIsNone(parse_ping_latency("Host unreachable"))

    def test_rates(self):
        self.assertEqual(calc_rates((100, 80), (300, 100), 2), (100, 10))
        self.assertEqual(calc_rates((300, 100), (100, 80), 2), (0, 0))
        self.assertEqual(calc_rates((0, 0), (50, 90), 0), (0, 0))
        self.assertEqual(format_rate(2048), "2.0 KB/s")

    @patch("netpulse.network.platform.system", return_value="Windows")
    @patch("netpulse.network.subprocess.run")
    def test_windows_ping_invocation(self, fake_run, _system):
        fake_run.return_value = Mock(returncode=0, stdout="Odpowiedz czas=19ms", stderr="")
        result = probe("1.1.1.1", "ICMP")
        self.assertTrue(result.ok)
        self.assertEqual(result.latency_ms, 19)
        args = fake_run.call_args.args[0]
        self.assertEqual(args[:3], ["ping", "-n", "1"])
        self.assertFalse(fake_run.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()

import time
import unittest

from backend.downloads import DownloadJob, SPEED_FLOOR_BPS, STALL_UI_SECONDS


def _job(**kw):
    j = DownloadJob(job_id="t", repo="fake/not-on-disk")
    j.state = "running"
    j.total_bytes = 10_000_000
    j.started_at = time.time() - 10
    for k, v in kw.items():
        setattr(j, k, v)
    return j


class DownloadSerializeTests(unittest.TestCase):
    def test_healthy_shows_eta(self):
        s = _job(_speed_bps=5_000_000.0, _last_progress_at=time.time()).serialize()
        self.assertFalse(s["stalled"])
        self.assertIsNotNone(s["eta_seconds"])
        self.assertGreater(s["eta_seconds"], 0)

    def test_tiny_decaying_speed_gives_no_eta(self):
        # The old bug: EMA speed decays toward but never reaches 0, so ">0" was
        # true and ETA blew up (1e+90). A real floor must suppress the ETA.
        s = _job(_speed_bps=1e-80, _last_progress_at=time.time()).serialize()
        self.assertIsNone(s["eta_seconds"])
        self.assertLess(1e-80, SPEED_FLOOR_BPS)

    def test_stall_detected_and_no_eta(self):
        s = _job(_speed_bps=5_000_000.0,
                 _last_progress_at=time.time() - (STALL_UI_SECONDS + 50),
                 attempt=3, retry_reason="stalled — no data for 75s").serialize()
        self.assertTrue(s["stalled"])
        self.assertIsNone(s["eta_seconds"])
        self.assertEqual(s["attempt"], 3)
        self.assertIn("stalled", s["retry_reason"])

    def test_terminal_state_clears_speed(self):
        s = _job(state="done", _speed_bps=5_000_000.0).serialize()
        self.assertEqual(s["speed_bps"], 0.0)
        self.assertIsNone(s["eta_seconds"])


if __name__ == "__main__":
    unittest.main()

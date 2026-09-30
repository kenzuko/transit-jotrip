"""Provenance tests: refreshing a cached PQE board must never refresh its source time."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from collector.collect import previous_operator_last_success, previous_operator_rows

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime.fromisoformat("2026-10-01T00:48:00+07:00")
DAY = "2026-10-01"
ACTUAL = "2026-10-01T00:12:00+07:00"


def snapshot(status, **meta):
    return {
        "generated_at": "2026-10-01T00:47:00+07:00",
        "sources": {"registry": {"phu_quoc_express": {"status": status, **meta}}},
        "departures": [
            {"operator": "Phú Quốc Express", "departure_time": DAY + "T06:00:00+07:00"},
            {"operator": "Phú Quốc Express", "departure_time": "2026-09-30T06:00:00+07:00"},
        ],
    }


class PQECacheProvenanceTests(unittest.TestCase):
    def test_last_real_success_from_verified_ok_collection(self):
        prior = snapshot("ok", checked_at=ACTUAL)
        self.assertEqual(previous_operator_last_success(prior, "phu_quoc_express", DAY, NOW), ACTUAL)

    def test_repeated_cached_collections_never_renew_source_time(self):
        prior = snapshot("cached", last_success_at=ACTUAL, last_success_verified=True)
        for minute in (48, 49, 59):
            now = NOW.replace(minute=minute)
            observed = previous_operator_last_success(prior, "phu_quoc_express", DAY, now)
            self.assertEqual(observed, ACTUAL)
            prior = snapshot("cached", last_success_at=observed, last_success_verified=True)
            prior["generated_at"] = now.isoformat()

    def test_legacy_cache_does_not_borrow_recent_snapshot_generated_at(self):
        prior = snapshot("cached")
        self.assertIsNone(previous_operator_last_success(prior, "phu_quoc_express", DAY, NOW))
        self.assertNotEqual(prior["generated_at"], ACTUAL)

    def test_legacy_caches_with_plausible_but_unverified_times_are_rejected(self):
        # Old code used previous snapshot generation time for cached rows.
        prior = snapshot("cached", last_success_at="2026-10-01T00:47:00+07:00")
        self.assertIsNone(previous_operator_last_success(prior, "phu_quoc_express", DAY, NOW))
        prior["sources"]["registry"]["phu_quoc_express"]["last_success_verified"] = False
        self.assertIsNone(previous_operator_last_success(prior, "phu_quoc_express", DAY, NOW))

    def test_source_error_or_empty_never_claims_success(self):
        for status in ("error", "empty", "unknown"):
            with self.subTest(status=status):
                prior = snapshot(status, checked_at=ACTUAL, last_success_at=ACTUAL)
                self.assertIsNone(previous_operator_last_success(prior, "phu_quoc_express", DAY, NOW))

    def test_old_day_unparseable_naive_and_future_timestamps_are_rejected(self):
        values = [
            "2026-09-30T23:59:00+07:00",
            "not-a-time",
            "2026-10-01T00:12:00",  # timezone missing
            "2026-10-01T01:00:00+07:00",
        ]
        for stamp in values:
            with self.subTest(stamp=stamp):
                self.assertIsNone(previous_operator_last_success(
                    snapshot("cached", last_success_at=stamp, last_success_verified=True),
                    "phu_quoc_express", DAY, NOW,
                ))

    def test_iso_utc_timestamp_reuses_actual_same_day_time(self):
        actual_utc = "2026-09-30T17:12:00Z"
        self.assertEqual(previous_operator_last_success(
            snapshot("cached", last_success_at=actual_utc, last_success_verified=True),
            "phu_quoc_express", DAY, NOW,
        ), actual_utc)

    def test_missing_source_metadata_does_not_infer_snapshot_timestamp(self):
        prior = {"generated_at": NOW.isoformat(), "sources": {"registry": {}}}
        self.assertIsNone(previous_operator_last_success(prior, "phu_quoc_express", DAY, NOW))

    def test_cached_rows_never_cross_service_day(self):
        prior = snapshot("ok", checked_at=ACTUAL)
        rows = previous_operator_rows(prior, "Phú Quốc Express", DAY)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["departure_time"].startswith(DAY))
        self.assertNotIn("generated_at", rows[0])


if __name__ == "__main__":
    unittest.main()

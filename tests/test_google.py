"""Offline tests for the Google Maps module. Uses a fake key and mocked HTTP."""
import os
import unittest
from unittest import mock

from src import acq, geo, geo_google

FAKE = "FAKE-KEY-FOR-TESTS-123"
LAT, LNG = 30.3200, -86.1000


class Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._p, self.text = status, payload, text

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p


def place(name, dlat, dlng):
    return {"displayName": {"text": name}, "location": {"latitude": LAT + dlat, "longitude": LNG + dlng},
            "types": ["natural_feature"]}


def router(places=None, walk_m=140, eateries=11, calls=None):
    """Fake requests.post that answers each Google endpoint."""
    def fake(url, json=None, timeout=None, headers=None):
        if calls is not None:
            calls.append((url, headers))
        if "searchText" in url:
            return Resp(200, {"places": places or []})
        if "searchNearby" in url:
            return Resp(200, {"places": [{"id": str(i)} for i in range(eateries)]})
        if "computeRoutes" in url:
            return Resp(200, {"routes": [{"distanceMeters": walk_m, "duration": "100s"}]} if walk_m else {})
        raise AssertionError(url)
    return fake


class GoogleTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": FAKE})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_missing_key_is_unavailable(self):
        with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": ""}):
            self.assertFalse(geo_google.available())
            with self.assertRaises(geo.GeoUnavailable):
                geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300}])

    def test_beach_walk_and_eateries(self):
        rules = [{"signal": "beach", "max_m": 300}, {"signal": "walkable", "min_pois": 8, "radius_m": 800}]
        with mock.patch.object(geo_google.requests, "post",
                               side_effect=router([place("Dune Allen Beach", -0.0012, 0)], 140, 11)):
            g = geo_google.get_geo(LAT, LNG, rules)
        self.assertEqual(g["beach_m"], 140)
        self.assertEqual(g["pois_walkable"], 11)
        self.assertEqual(g["names"]["beach"], "Dune Allen Beach")
        ev = geo.evaluate_location(g, rules)
        self.assertTrue(ev["ok"])
        self.assertTrue(any("Dune Allen Beach" in m for m in ev["matched"]))
        self.assertTrue(any("NOT checked" in n for n in ev["notes"]))

    def test_far_beach_does_not_match(self):
        far = place("Far Beach", -0.02, 0)  # ~2.2 km
        with mock.patch.object(geo_google.requests, "post", side_effect=router([far], 2900, 0)):
            g = geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300}])
        self.assertIsNone(g["beach_m"])
        self.assertFalse(geo.evaluate_location(g, [{"signal": "beach", "max_m": 300}])["ok"])

    def test_long_walk_route_rejects_even_if_straight_line_is_close(self):
        near = place("Bay Beach", -0.0015, 0)  # ~165 m straight line
        rules = [{"signal": "beach", "max_m": 300}]
        with mock.patch.object(geo_google.requests, "post", side_effect=router([near], 900, 0)):
            g = geo_google.get_geo(LAT, LNG, rules)
        self.assertEqual(g["beach_m"], 900)
        self.assertFalse(geo.evaluate_location(g, rules)["ok"])

    def test_no_walking_route_means_no_match(self):
        near = place("Island Beach", -0.0015, 0)
        with mock.patch.object(geo_google.requests, "post", side_effect=router([near], None, 0)):
            g = geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300}])
        self.assertIsNone(g["beach_m"])

    def test_key_sent_in_header_never_url_or_body(self):
        calls = []
        with mock.patch.object(geo_google.requests, "post",
                               side_effect=router([place("B", -0.001, 0)], 120, 9, calls)):
            geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300},
                                          {"signal": "walkable", "min_pois": 8}])
        self.assertTrue(calls)
        for url, headers in calls:
            self.assertNotIn(FAKE, url)
            self.assertEqual(headers["X-Goog-Api-Key"], FAKE)

    def test_api_error_message_surfaces_without_the_key(self):
        err = {"error": {"message": f"Places API (New) has not been used in project 123 {FAKE} before"}}
        with mock.patch.object(geo_google.requests, "post", return_value=Resp(403, err)):
            with self.assertRaises(geo.GeoUnavailable) as cm:
                geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300}])
        msg = str(cm.exception)
        self.assertIn("403", msg)
        self.assertIn("has not been used", msg)
        self.assertNotIn(FAKE, msg)

    def test_timeout_and_connection_errors_are_geo_unavailable(self):
        for exc in (geo_google.requests.exceptions.Timeout(), OSError("boom")):
            with mock.patch.object(geo_google.requests, "post", side_effect=exc):
                with self.assertRaises(geo.GeoUnavailable) as cm:
                    geo_google.get_geo(LAT, LNG, [{"signal": "beach", "max_m": 300}])
                self.assertNotIn(FAKE, str(cm.exception))

    def test_acq_uses_google_when_key_set_and_osm_otherwise(self):
        with mock.patch.object(acq.geo_google, "get_geo", return_value={"g": 1}) as g, \
             mock.patch.object(acq, "_get_geo_osm", return_value={"o": 1}) as o:
            self.assertEqual(acq.get_geo(LAT, LNG, []), {"g": 1})
            with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": ""}):
                self.assertEqual(acq.get_geo(LAT, LNG, []), {"o": 1})
        g.assert_called_once()
        o.assert_called_once()


if __name__ == "__main__":
    unittest.main()

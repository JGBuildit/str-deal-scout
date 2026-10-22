"""
Offline tests: no network needed.  Run with:  python -m unittest discover -s tests -v
Map fixtures are built around a property at LAT0/LNG0 with features placed at
known distances, so the geometry can be checked against exact answers.
"""
import math
import os
import tempfile
import unittest
from unittest import mock

from src import acq, airdna, geo
from src.acq_config import ACQ_MARKETS

LAT0, LNG0 = 30.3200, -86.1000
M_LAT = 110540.0
M_LNG = 111320.0 * math.cos(math.radians(LAT0))


def pt(east_m, north_m):
    return {"lat": LAT0 + north_m / M_LAT, "lon": LNG0 + east_m / M_LNG}


def way(tags, *pts):
    return {"type": "way", "tags": tags, "geometry": [pt(*p) for p in pts]}


MARKET = next(m for m in ACQ_MARKETS if m["key"] == "scenic_30a")
MCCALL = next(m for m in ACQ_MARKETS if m["key"] == "mccall_id")


class GeometryTests(unittest.TestCase):
    def test_beach_distance_one_block_quiet_street(self):
        els = [way({"natural": "beach"}, (-500, -150), (500, -150)),
               way({"highway": "residential"}, (-500, -60), (500, -60))]
        g = geo.analyze(LAT0, LNG0, els)
        self.assertAlmostEqual(g["beach_m"], 150, delta=3)
        self.assertFalse(g["crosses_busy"]["beach"])
        ev = geo.evaluate_location(g, MARKET["location_rules"])
        self.assertTrue(ev["ok"])
        self.assertIn("~1 block", ev["matched"][0])

    def test_busy_road_between_property_and_beach_rejects(self):
        els = [way({"natural": "beach"}, (-500, -200), (500, -200)),
               way({"highway": "primary"}, (-500, -100), (500, -100))]
        g = geo.analyze(LAT0, LNG0, els)
        self.assertTrue(g["crosses_busy"]["beach"])
        ev = geo.evaluate_location(g, [{"signal": "beach", "max_m": 300}])
        self.assertFalse(ev["ok"])
        self.assertTrue(any("busy road" in n for n in ev["notes"]))

    def test_secondary_road_is_noted_not_rejected(self):
        els = [way({"natural": "beach"}, (-500, -200), (500, -200)),
               way({"highway": "secondary"}, (-500, -100), (500, -100))]
        g = geo.analyze(LAT0, LNG0, els)
        ev = geo.evaluate_location(g, [{"signal": "beach", "max_m": 300}])
        self.assertTrue(ev["ok"])
        self.assertTrue(any("secondary" in n for n in ev["notes"]))

    def test_beach_too_far(self):
        els = [way({"natural": "beach"}, (-500, -450), (500, -450))]
        g = geo.analyze(LAT0, LNG0, els)
        self.assertFalse(geo.evaluate_location(g, [{"signal": "beach", "max_m": 300}])["ok"])

    def test_fronts_busy_road(self):
        els = [way({"highway": "trunk"}, (-500, 15), (500, 15))]
        g = geo.analyze(LAT0, LNG0, els)
        self.assertTrue(g["fronts_busy_road"])

    def test_lake_relation_members(self):
        rel = {"type": "relation", "tags": {"natural": "water", "name": "Payette Lake"},
               "members": [{"geometry": [pt(-300, 120), pt(300, 120)]}]}
        g = geo.analyze(LAT0, LNG0, [rel])
        self.assertAlmostEqual(g["lake_m"], 120, delta=3)
        self.assertTrue(geo.evaluate_location(g, MCCALL["location_rules"])["ok"])

    def test_unnamed_pond_ignored(self):
        els = [way({"natural": "water"}, (-50, 20), (50, 20))]
        self.assertIsNone(geo.analyze(LAT0, LNG0, els)["lake_m"])

    def test_walkable_pois(self):
        nodes = [{"type": "node", "tags": {"amenity": "restaurant"}, **{"lat": pt(100 + i * 20, 50)["lat"],
                  "lon": pt(100 + i * 20, 50)["lon"]}} for i in range(9)]
        far = {"type": "node", "tags": {"amenity": "bar"}, **pt(5000, 5000)}
        g = geo.analyze(LAT0, LNG0, nodes + [far])
        self.assertEqual(g["pois_walkable"], 9)
        self.assertTrue(geo.evaluate_location(g, [{"signal": "walkable", "min_pois": 8}])["ok"])

    def test_ski_lift_distance(self):
        ski = [way({"aerialway": "chair_lift"}, (400, 300), (900, 700))]
        g = geo.analyze(LAT0, LNG0, [], ski)
        self.assertAlmostEqual(g["ski_m"], 500, delta=5)
        self.assertTrue(geo.evaluate_location(g, [{"signal": "ski", "max_m": 600}])["ok"])
        self.assertFalse(geo.evaluate_location(g, [{"signal": "ski", "max_m": 400}])["ok"])

    def test_no_network_raises(self):
        with mock.patch.dict(os.environ, {"GEO_PROVIDER": "off"}):
            with self.assertRaises(geo.GeoUnavailable):
                geo.get_geo(LAT0, LNG0, MARKET["location_rules"])


LISTING = {"address": "1 Test Ln, Santa Rosa Beach, FL", "price": 1_200_000, "bedrooms": 4,
           "bathrooms": 3, "property_type": "Single Family", "lat": LAT0, "lng": LNG0,
           "description": "Walk to the beach. Private heated pool.", "hoa_fee": None, "features": {}}
NO_AIRDNA = {"market": [], "property": {}}


class AmenityTests(unittest.TestCase):
    def test_pool_table_is_not_a_pool(self):
        a = acq.detect_amenities({"description": "Game room with pool table and bar"})
        self.assertFalse(a["pool"])

    def test_private_pool(self):
        self.assertTrue(acq.detect_amenities({"description": "Private heated pool and hot tub"})["pool"])

    def test_community_pool_only(self):
        a = acq.detect_amenities({"description": "Access to the community pool"})
        self.assertFalse(a["pool"])
        self.assertTrue(a["shared_pool_only"])

    def test_hot_tub_and_sauna(self):
        a = acq.detect_amenities({"description": "Hot tub on the deck, steam sauna in basement"})
        self.assertTrue(a["hot_tub"] and a["sauna"])


class ExclusionTests(unittest.TestCase):
    def test_filters(self):
        self.assertIn("bedrooms", acq.exclusion_reason({**LISTING, "bedrooms": 2}))
        self.assertIn("bathrooms", acq.exclusion_reason({**LISTING, "bathrooms": 1}))
        self.assertIn("property type", acq.exclusion_reason({**LISTING, "property_type": "Land"}))
        self.assertEqual(acq.exclusion_reason(LISTING), "")


class FinanceTests(unittest.TestCase):
    def test_debt_service_matches_known_payment(self):
        # $900,000 loan, 7.25%, 30 yrs -> $6,139.5/mo (standard amortization)
        loan, ds = acq._annual_debt_service(1_200_000)
        self.assertAlmostEqual(loan, 900_000)
        self.assertAlmostEqual(ds / 12, 6139.6, delta=1.0)

    def test_deduction_math(self):
        am = acq.detect_amenities(LISTING)
        rev = acq.revenue_basis(LISTING, MARKET, am, NO_AIRDNA)
        f = acq.financials(LISTING, MARKET, am, rev, False)
        building = 1_200_000 * (1 - MARKET["land_pct"])
        short = building * (0.25 + 0.04)
        ffe = 15_000 + 9_000 * 4
        expected = short + ffe + (building - short) / 39 * 0.9
        self.assertAlmostEqual(f["year1_deduction"], expected, delta=2)

    def test_estimate_revenue_is_never_a_hard_pass(self):
        with mock.patch.object(acq, "get_geo", return_value=_good_geo()):
            r = acq.score_acq(_rich(LISTING), MARKET, NO_AIRDNA)
        if r["status"] != "FAIL":
            self.assertEqual(r["status"], "PROVISIONAL")
        self.assertEqual(r["adr_source"], "estimate")

    def test_airdna_data_allows_pass(self):
        data = {"market": [{"market_key": "scenic_30a", "bedrooms": 4, "adr": 2000, "occ": .60,
                            "pool": None, "hot_tub": None, "date": "2026-10-17"}], "property": {}}
        with mock.patch.object(acq, "get_geo", return_value=_good_geo()):
            r = acq.score_acq(LISTING, MARKET, data)
        self.assertEqual(r["adr_source"], "airdna-market")
        self.assertEqual(r["status"], "PASS", r["flags"])

    def test_negative_cash_flow_fails_without_map_call(self):
        weak = {"market": [{"market_key": "scenic_30a", "bedrooms": 4, "adr": 100, "occ": .2,
                            "pool": None, "hot_tub": None, "date": ""}], "property": {}}
        with mock.patch.object(acq, "get_geo", side_effect=AssertionError("map called")) as g:
            r = acq.score_acq(LISTING, MARKET, weak)
        self.assertEqual(r["status"], "FAIL")
        g.assert_not_called()

    def test_map_unavailable_gives_needs_map(self):
        data = {"market": [{"market_key": "scenic_30a", "bedrooms": 4, "adr": 2000, "occ": .60,
                            "pool": None, "hot_tub": None, "date": ""}], "property": {}}
        with mock.patch.object(acq, "get_geo", side_effect=geo.GeoUnavailable("offline")):
            r = acq.score_acq(LISTING, MARKET, data)
        self.assertEqual(r["status"], "NEEDS_MAP")

    def test_location_fail_blocks(self):
        data = {"market": [{"market_key": "scenic_30a", "bedrooms": 4, "adr": 2000, "occ": .60,
                            "pool": None, "hot_tub": None, "date": ""}], "property": {}}
        far = geo.analyze(LAT0, LNG0, [way({"natural": "beach"}, (-500, -900), (500, -900))])
        with mock.patch.object(acq, "get_geo", return_value=far):
            r = acq.score_acq(LISTING, MARKET, data)
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any("location" in f for f in r["fails"]))


def _good_geo():
    return geo.analyze(LAT0, LNG0, [way({"natural": "beach"}, (-500, -120), (500, -120))])


def _rich(listing):
    return {**listing, "price": 1_200_000}


class AirdnaTests(unittest.TestCase):
    def _dir(self, market="", prop=""):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "market_stats.csv"), "w") as f:
            f.write("market_key,bedrooms,adr,occupancy,pool,hot_tub,source_date,notes\n" + market)
        with open(os.path.join(d, "rentalizer.csv"), "w") as f:
            f.write("address,annual_revenue,adr,occupancy,source_date,notes\n" + prop)
        return d

    def test_parses_messy_values(self):
        d = self._dir('scenic_30a,4,"$640",51%,y,,2026-10-17,x\nscenic_30a,5,700,52,,,,\n')
        data = airdna.load(d)
        self.assertEqual(data["market"][0]["adr"], 640)
        self.assertAlmostEqual(data["market"][0]["occ"], .51)
        self.assertAlmostEqual(data["market"][1]["occ"], .52)

    def test_amenity_specific_row_preferred(self):
        d = self._dir("scenic_30a,4,500,0.45,,,,generic\nscenic_30a,4,640,0.51,y,,,pool\n")
        data = airdna.load(d)
        pool = airdna.lookup(data, "scenic_30a", "x", 4, True, False)
        nopool = airdna.lookup(data, "scenic_30a", "x", 4, False, False)
        self.assertEqual(pool["adr"], 640)
        self.assertEqual(nopool["adr"], 500)

    def test_property_override_wins(self):
        d = self._dir("scenic_30a,4,500,0.45,,,,\n", "1 Test Ln Santa Rosa Beach FL,142000,,,2026-10-17,r\n")
        data = airdna.load(d)
        r = airdna.lookup(data, "scenic_30a", "1 test ln, Santa Rosa Beach, FL", 4, False, False)
        self.assertEqual(r["source"], "airdna-property")
        self.assertEqual(r["annual_revenue"], 142000)

    def test_annual_revenue_column_is_read(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "market_stats.csv"), "w") as f:
            f.write("market_key,bedrooms,annual_revenue,adr,occupancy,pool,hot_tub,source_date,notes\n"
                    "scenic_30a,4,\"$108,900\",766.62,0.57,,,2026-10-22,x\n"
                    "scenic_30a,5,167000,,,,,2026-10-22,revenue only\n")
        data = airdna.load(d)
        self.assertEqual(data["market"][0]["annual_revenue"], 108900)
        self.assertEqual(data["market"][1]["annual_revenue"], 167000)  # no adr/occ needed

    def test_old_format_without_annual_revenue_still_loads(self):
        d = self._dir("scenic_30a,4,640,0.51,,,,x\n")
        data = airdna.load(d)
        self.assertIsNone(data["market"][0]["annual_revenue"])

    def test_model_uses_airdna_annual_revenue_not_adr_x_occ(self):
        row = {"market_key": "scenic_30a", "bedrooms": 4, "annual_revenue": 109000,
               "adr": 767, "occ": 0.57, "pool": None, "hot_tub": None, "date": "2026-10-22"}
        am = acq.detect_amenities(LISTING)
        rev = acq.revenue_basis(LISTING, MARKET, am, {"market": [row], "property": {}})
        self.assertEqual(rev["gross"], 109000)
        self.assertLess(rev["gross"], 767 * 0.57 * 365 * 0.75)

    def test_missing_files_ok(self):
        data = airdna.load(tempfile.mkdtemp())
        self.assertEqual(data, {"market": [], "property": {}})


if __name__ == "__main__":
    unittest.main()

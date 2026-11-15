# Created by nc.ai 1.2.15 on Papasha 2026-11-15 12:15:00
"""Вкладка «Добыча»: справочник материалов, индекс цен, разбор Spansh."""
import time

from edhud import mining, miningsearch, prices
from edhud.miningui import rows_from_remote, rows_from_state
from edhud.model import Body, GameState


# --------------------------------------------------------------- справочник
def test_material_grades_and_rows():
    assert mining.material_grade("Polonium") == 4
    assert mining.material_grade("Iron") == 1
    assert mining.material_grade("Нет такого") == 0

    materials = {"Iron": 23.5, "Polonium": 1.8, "Carbon": 10.8}
    rows = mining.material_rows(materials)
    assert rows[0][0] == "Polonium"  # редкое вперёд
    assert rows[0][2] == 4
    assert mining.format_materials(materials, limit=2).startswith("Polonium 1.8%")


def test_surface_site_signal_detection():
    assert mining.has_surface_site({"Planetary Mining Location": 6})
    assert mining.has_surface_site({"Geological": 3})
    assert not mining.has_surface_site({"Biological": 2})
    assert not mining.has_surface_site(None)


def test_ring_revenue_and_kind():
    hotspots = {"Alexandrite": 2, "Platinum": 1}
    assert mining.ring_revenue(hotspots, 100) == 236_000 * 100
    assert mining.ring_revenue(hotspots, 0) == 0
    assert mining.ring_kind([{"type": "Icy"}, {"type": "Rocky"}]) == "Icy · Rocky"


# -------------------------------------------------------------- индекс цен
def test_market_index_ingests_journal_and_eddn(tmp_path):
    index = prices.MarketIndex(tmp_path / "prices.json")

    event = {
        "event": "Market",
        "StarSystem": "Sol",
        "StationName": "Galileo",
        "Items": [
            {"Name": "Platinum", "SellPrice": 81_000},
            {"Name": "Gold", "SellPrice": 40_000},
            {"Name": "Biowaste", "SellPrice": 100},  # не добывается — мимо
        ],
    }
    assert index.ingest_market_event(event) == 2
    assert index.best("Platinum").price == 81_000
    assert index.best("Biowaste") is None

    better = {
        "event": "commodity",
        "systemName": "Achenar",
        "stationName": "Dawes",
        "commodities": [{"name": "Platinum", "sellPrice": 95_000}],
    }
    assert index.ingest_commodity(better) == 1
    quote = index.best("platinum")
    assert quote.price == 95_000 and quote.system == "Achenar"

    worse = dict(better, commodities=[{"name": "Platinum", "sellPrice": 1}])
    assert index.ingest_commodity(worse) == 0  # хуже — не перезаписываем
    assert index.best("Platinum").price == 95_000

    index.save()
    reloaded = prices.MarketIndex(tmp_path / "prices.json")
    assert len(reloaded) == 2
    assert reloaded.best("Platinum").price == 95_000


def test_market_index_prunes_stale_quotes(tmp_path):
    index = prices.MarketIndex(tmp_path / "prices.json", max_age_days=1.0)
    index.add("Platinum", "Old", "Old", 1000, updated=time.time() - 3 * 86400)
    assert index.prune() == 1
    assert len(index) == 0


# ------------------------------------------------------------------- Spansh
SPANSH_BODY = {
    "name": "Mercury",
    "system_name": "Sol",
    "system_id64": 10477373803,
    "body_id": 1,
    "subtype": "Metal-rich body",
    "distance": 0.0,
    "distance_to_arrival": 156.3,
    "is_landable": True,
    "signals": [
        {"name": "Planetary Mining Location", "count": 6},
        {"name": "Human", "count": 6},
    ],
    "materials": [{"name": "Iron", "share": 23.5}, {"name": "Polonium", "share": 1.8}],
    "rings": [],
}


def test_parse_spansh_body():
    body = miningsearch.parse_body(SPANSH_BODY)
    assert body is not None
    assert body.system == "Sol" and body.name == "Mercury"
    assert body.has_surface_site()
    assert body.share("Polonium") == 1.8
    assert body.best_material()[0] == "Polonium"
    assert body.signals_label() == "Planetary Mining Location ×6"


def test_pick_surface_sorts_by_material_share():
    rich = miningsearch.parse_body(SPANSH_BODY)
    poor = miningsearch.parse_body(
        {
            **SPANSH_BODY,
            "name": "Callisto",
            "materials": [{"name": "Polonium", "share": 0.4}],
        }
    )
    assert rich is not None and poor is not None
    picked = miningsearch.pick_surface([poor, rich], "Polonium")
    assert [body.name for body in picked] == ["Mercury", "Callisto"]

    # без материала — по расстоянию, но фильтр по точкам добычи остаётся
    star = miningsearch.parse_body({**SPANSH_BODY, "name": "Star", "is_landable": False})
    assert star is not None
    assert [body.name for body in miningsearch.pick_surface([rich, star])] == ["Mercury"]


def test_pick_rings_prefers_current_system():
    ringed = miningsearch.parse_body({**SPANSH_BODY, "name": "5", "rings": [{"type": "Icy"}]})
    local = miningsearch.parse_body({**SPANSH_BODY, "name": "6", "rings": [{"type": "Metallic"}]})
    assert ringed is not None and local is not None
    picked = miningsearch.pick_rings([ringed, local], "Sol")
    assert len(picked) == 2


# ------------------------------------------------------------- построение строк
def _state_with_bodies() -> GameState:
    state = GameState()
    state.system.name = "Test"
    geo = Body(body_id=1, name="Test 1", planet_class="Rocky body", landable=True)
    geo.geo_signals = 2
    geo.materials = {"Iron": 20.0, "Polonium": 2.5}
    geo.distance_ls = 500.0
    ring = Body(body_id=2, name="Test 2", planet_class="Icy body")
    ring.has_rings = True
    ring.hotspots = {"Alexandrite": 3}
    ring.materials = {"Iron": 10.0}
    state.system.bodies[1] = geo
    state.system.bodies[2] = ring
    return state


def test_rows_from_state(tmp_path):
    state = _state_with_bodies()
    index = prices.MarketIndex(tmp_path / "prices.json")
    index.add("Alexandrite", "Somewhere", "Sol", 250_000)

    rows = rows_from_state(state, index)
    assert len(rows) == 2
    geo_row = next(row for row in rows if row.body == "Test 1")
    assert geo_row.material == "Polonium" and geo_row.share == 2.5
    ring_row = next(row for row in rows if row.body == "Test 2")
    assert ring_row.price == 250_000 and ring_row.price_exact
    assert ring_row.hotspots == {"Alexandrite": 3}


def test_rows_from_remote_uses_price_index(tmp_path):
    body = miningsearch.parse_body(
        {**SPANSH_BODY, "rings": [{"type": "Metallic"}]}
    )
    assert body is not None
    index = prices.MarketIndex(tmp_path / "prices.json")
    rows = rows_from_remote([body], "Platinum", index)
    # поверхностная точка + кольцо
    assert len(rows) == 2
    ring_row = next(row for row in rows if row.rings)
    assert ring_row.price == mining.hotspot_avg_price("Platinum")  # индекса нет — средняя
    assert not ring_row.price_exact

# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:22:52
"""Модель отображения HUD: из GameState в строки/сегменты для рендера.

Чистый слой без зависимостей от UI — его используют и tkinter-оверлей, и
терминальный режим, и тесты.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import bio, codex, values
from .model import Body, GameState


@dataclass
class Segment:
    text: str
    style: str = "text"


@dataclass
class Row:
    segments: list[Segment] = field(default_factory=list)
    # правый хвост строки: рисуется целиком, даже если левая часть не влезает
    tail: list[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments + self.tail)


@dataclass
class HudView:
    route_row: Row
    body_row: Row
    detail: list[Row]
    progress: tuple[int, int]
    dots: list[bool]
    alert: str | None = None
    accent: str = "fg"
    hint: str | None = None

    @property
    def fraction(self) -> float:
        done, total = self.progress
        if total <= 0:
            return 0.0
        return max(0.0, min(1.0, done / total))

    def plain(self) -> list[str]:
        lines = [self.route_row.text, self.body_row.text] + [row.text for row in self.detail]
        if self.hint:
            lines.append(self.hint)
        return lines


# ------------------------------------------------------------------ форматтеры
def _ly(value: float) -> str:
    return f"{value:,.1f}".replace(",", " ") if value else "—"


def _jumps_word(count: int) -> str:
    n = abs(int(count)) % 100
    if 11 <= n <= 14:
        return "прыжков"
    last = n % 10
    if last == 1:
        return "прыжок"
    if 2 <= last <= 4:
        return "прыжка"
    return "прыжков"


def _ls(value: float) -> str:
    if not value:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн ls"
    if value >= 10_000:
        return f"{value / 1000:,.0f} тыс ls".replace(",", " ")
    return f"{value:,.0f} ls".replace(",", " ")


def _meters(value: float) -> str:
    return f"{value:,.0f} м".replace(",", " ")


def _genuses(body: Body, limit: int = 4) -> str:
    if not body.genuses:
        return ""
    parts = []
    for key, count in list(body.genuses.items())[:limit]:
        name = codex.display_name(key)
        parts.append(f"{name}×{count}" if count > 1 else name)
    if len(body.genuses) > limit:
        parts.append(f"+{len(body.genuses) - limit}")
    return ", ".join(parts)


def _body_value_text(body: Body, odyssey: bool = True) -> tuple[str, str]:
    """(текст, стиль) стоимости тела: скан или скан+DSS, с множителем."""
    breakdown = values.body_values(body, odyssey=odyssey)
    if breakdown is None:
        return "", "muted"
    if body.dss_scanned:
        text = f"≈{values.credits(breakdown.mapped)}"
    else:
        text = f"≈{values.credits(breakdown.scan)}"
    return text, "accent"


def _route_row(state: GameState, cfg) -> tuple[Row, tuple[int, int], list[bool], str]:
    route = state.route
    system = state.system.name
    row = Row()
    if not route.hops:
        row.segments.append(Segment("МАРШРУТ ", "dim"))
        if state.fsd_target:
            row.segments.append(Segment(state.fsd_target, "accent"))
            if state.jumps_in_route:
                row.segments.append(Segment(f" · {state.jumps_in_route} прыжк.", "text"))
        else:
            row.segments.append(Segment("не задан — проложите в карте галактики", "muted"))
        _append_carrier(row, state)
        return row, (0, 0), [], "muted"

    done, total = route.progress(system)
    next_hop = route.next_hop(system)
    remaining = route.remaining(system)
    remaining_ly = route.distance_remaining(system, state.position)

    row.segments.append(Segment("МАРШРУТ ", "dim"))
    row.segments.append(Segment(f"{done}/{total}", "fg"))
    if next_hop:
        star = f"{next_hop.star_class}" if next_hop.star_class else "?"
        row.segments.append(Segment("  →  ", "muted"))
        row.segments.append(Segment(next_hop.system, "accent"))
        row.segments.append(Segment(f" ({star} · {_ly(next_hop.distance)} ly)", "muted"))
        if remaining:
            row.segments.append(Segment("   осталось ", "dim"))
            row.segments.append(
                Segment(f"{remaining} {_jumps_word(remaining)} из {total}", "text")
            )
            if remaining_ly:
                row.segments.append(Segment(f" · {_ly(remaining_ly)} ly", "muted"))
        row.segments.append(Segment("  ", "text"))
        if next_hop.scoopable:
            row.segments.append(Segment("заправка ✔", "ok"))
        else:
            row.segments.append(Segment("не заправка", "warn"))
    else:
        row.segments.append(Segment("  финиш маршрута", "ok"))

    if route.locked:
        row.segments.append(Segment("  [залочен]", "warn"))
    _append_carrier(row, state)

    dots_total = max(1, total)
    dots = [i < done for i in range(min(dots_total, 40))]
    accent = "fg" if remaining else "ok"
    return row, (done, total), dots, accent


def _body_row(state: GameState, cfg) -> Row:
    row = Row()
    body = state.body_for_status() or state.current_body()
    row.segments.append(Segment("ТЕЛО ", "dim"))
    if body is None:
        name = state.system.name or "—"
        count = f" · тел {state.system.body_count}" if state.system.body_count else ""
        row.segments.append(Segment(f"{name}{count}", "muted"))
        return row

    body_class = body.planet_class or ("звезда" if body.is_star else "?")
    row.segments.append(Segment(body.name, "fg"))
    row.segments.append(Segment(f" · {body_class}", "muted"))
    if body.distance_ls:
        row.segments.append(Segment(f" · {_ls(body.distance_ls)}", "muted"))

    row.segments.append(Segment("   БИО ", "dim"))
    if body.bio_signals is None and not body.signals_known:
        row.segments.append(Segment("?", "muted"))
    elif not body.bio_signals:
        row.segments.append(Segment("0", "muted"))
    else:
        row.segments.append(Segment(str(body.bio_signals), "ok"))
        genuses = _genuses(body)
        if genuses:
            row.segments.append(Segment(f" ({genuses})", "muted"))
        if body.geo_signals:
            row.segments.append(Segment(f" · гео {body.geo_signals}", "muted"))

    if body.landable or body.bio_signals:
        row.segments.append(Segment("   DSS ", "dim"))
        if body.dss_scanned or body.genuses:
            row.segments.append(Segment("✔", "ok"))
        elif body.dss_remote:
            row.segments.append(Segment("~", "accent"))
        else:
            row.segments.append(Segment("✗", "warn"))

    value_text, value_style = _body_value_text(body, state.odyssey)
    if value_text:
        row.segments.append(Segment("   ", "text"))
        row.segments.append(Segment(value_text, value_style))
        if not body.was_discovered:
            row.segments.append(Segment(" ×2.6", "warn"))
    if body.remote:
        row.segments.append(Segment(f"   [{body.source or 'EDSM'}]", "accent"))

    organic = state.active_organic()
    if organic is not None:
        row.segments.append(Segment("   ПРОБЫ ", "dim"))
        row.segments.append(Segment(f"{organic.genus_en} {organic.scans_text}", "warn"))
        colony = state.colony_distance()
        if colony:
            dist, need = colony
            style = "bad" if dist < need else "ok"
            row.segments.append(Segment(f" · {_meters(dist)}/{need} м", style))

    if state.status.srv:
        row.segments.append(Segment("   [SRV]", "accent"))
    elif state.mode == "OnFoot":
        row.segments.append(Segment("   [пешком]", "accent"))
    if state.legacy:
        row.segments.append(Segment("   [Legacy 3.8]", "warn"))
    return row


def _organism_rows(state: GameState, body: Body) -> list[Row]:
    rows: list[Row] = []
    for organic in sorted(body.organisms.values(), key=lambda o: (o.analysed, o.last_ts), reverse=True):
        row = Row()
        style = "ok" if organic.analysed else "warn"
        row.segments.append(Segment("● ", style))
        row.segments.append(Segment(organic.label, "fg"))
        row.segments.append(Segment(f"  {organic.scans_text}", style))
        payout = organic.payout
        if payout:
            row.segments.append(Segment(f"  ≈{values.credits(payout)}", "muted"))
            if organic.first_logged:
                row.segments.append(Segment(" ×5 First Logged", "ok"))
            elif organic.was_logged is None:
                row.segments.append(Segment(" (base, First Logged ?)", "dim"))
        rows.append(row)
    return rows


def _value_row(state: GameState, body: Body) -> Row | None:
    breakdown = values.body_values(body, odyssey=state.odyssey)
    if breakdown is None:
        return None
    row = Row([Segment("стоимость: ", "dim")])
    row.segments.append(Segment(f"скан ≈{values.credits(breakdown.scan)}", "text"))
    row.segments.append(Segment(f" · с DSS ≈{values.credits(breakdown.mapped)}", "text"))
    if breakdown.first_discoverer:
        row.segments.append(Segment(f" · ×{values.DISCOVERY_MULTIPLIER:g} за первое открытие", "ok"))
    elif breakdown.first_mapper:
        row.segments.append(Segment(" · DSS первым (×8.1)", "ok"))
    if body.landable:
        if body.was_footfalled:
            row.segments.append(Segment(" · футфол уже был", "muted"))
        else:
            row.segments.append(Segment(" · чужого футфола нет: шанс на ×5 First Logged", "ok"))
    if body.discovered_by:
        row.segments.append(Segment(f" · открыл {body.discovered_by}", "muted"))
    if body.mapped_by:
        row.segments.append(Segment(f" · картографировал {body.mapped_by}", "muted"))
    return row


def _detail_rows(state: GameState, cfg, now: float) -> list[Row]:
    rows: list[Row] = []
    body = state.body_for_status() or state.current_body()
    max_pred = max(1, int(cfg.max_predictions))

    if body is not None:
        rows.extend(_organism_rows(state, body))
        value_row = _value_row(state, body)
        if value_row is not None:
            rows.append(value_row)

    if (
        body is not None
        and cfg.show_predictions
        and state.odyssey
        and (body.landable or body.genuses)
    ):
        predictions = bio.predict_for_body(body, state.system, limit=max_pred)
        if predictions:
            head = Row([Segment("предсказание: ", "dim")])
            head.segments.append(Segment(", ".join(sorted({p.genus for p in predictions})), "accent"))
            rows.append(head)
            for prediction in predictions[:max_pred]:
                row = Row([Segment("≈ ", "muted"), Segment(prediction.label, "text")])
                if prediction.reward:
                    row.segments.append(Segment(f"  {values.credits(prediction.reward)}", "muted"))
                rows.append(row)

    system_bio = [b for b in state.system.bio_bodies if b is not body]
    if system_bio:
        head = Row([Segment("био в системе: ", "dim")])
        head.segments.append(Segment(f"{len(system_bio)}", "ok"))
        rows.append(head)
        for candidate in sorted(system_bio, key=lambda b: b.distance_ls)[:6]:
            row = Row([Segment("• ", "muted"), Segment(candidate.name, "text")])
            row.segments.append(Segment(f"  {candidate.bio_signals} сигн.", "ok"))
            genuses = _genuses(candidate, limit=3)
            if genuses:
                row.segments.append(Segment(f" ({genuses})", "muted"))
            if candidate.dss_scanned or candidate.genuses:
                row.segments.append(Segment("  DSS ✔", "accent"))
            if candidate.remote:
                row.segments.append(Segment(f"  [{candidate.source or 'EDSM'}]", "muted"))
            row.segments.append(Segment(f"  {_ls(candidate.distance_ls)}", "muted"))
            rows.append(row)

    rows.append(_system_row(state))
    rows.append(_session_row(state))
    return rows


def _carrier_label(state: GameState) -> str | None:
    carrier = state.carrier
    if not carrier.known:
        return None
    who = carrier.callsign or carrier.name or "карриер"
    dist = state.carrier_distance_ly()
    if dist is None:
        where = carrier.system or "—"
        return f"{who} · {where}"
    if dist < 0.05:
        return f"{who} · здесь"
    text = f"{dist:,.1f}".replace(",", " ")
    return f"{who} · {text} ly"


def _append_carrier(row: Row, state: GameState) -> None:
    label = _carrier_label(state)
    if not label:
        return
    row.tail.append(Segment("   карриер ", "dim"))
    row.tail.append(Segment(label, "accent"))


def _system_row(state: GameState) -> Row:
    system = state.system
    scan_sum, mapped_sum = values.system_totals(system, odyssey=state.odyssey)
    row = Row([Segment("система: ", "dim")])
    if system.name:
        row.segments.append(Segment(system.name, "fg"))
        row.segments.append(Segment(" · ", "muted"))
    if system.discovered_by_me:
        row.segments.append(Segment("открыта вами", "ok"))
        row.segments.append(Segment(" · ", "muted"))
    row.segments.append(Segment(f"{len(system.bodies)} тел", "text"))
    if scan_sum:
        row.segments.append(Segment(f" · данных ≈{values.credits(scan_sum)}", "text"))
        row.segments.append(Segment(f" · с DSS ≈{values.credits(mapped_sum)}", "text"))
    if system.remote_scan_value:
        label = f" · EDSM ≈{values.credits(system.remote_scan_value)}"
        if system.remote_mapped_value:
            label += f" / с картами ≈{values.credits(system.remote_mapped_value)}"
        row.segments.append(Segment(label, "accent"))
    if system.remote_sources:
        row.segments.append(Segment(f" · догрузка: {', '.join(system.remote_sources)}", "muted"))
    if state.legacy:
        row.segments.append(Segment(" · Legacy 3.8 (без Odyssey-бонусов)", "warn"))
    return row


def _session_row(state: GameState) -> Row:
    row = Row([Segment("сессия: ", "dim")])
    row.segments.append(Segment(f"{state.session_jumps} прыжк.", "text"))
    fresh = "ok" if state.session_new_systems else "text"
    row.segments.append(Segment(f" · новых систем: {state.session_new_systems}", fresh))
    if state.avg_jump_sec >= 10:
        row.segments.append(Segment(f" · ~{state.avg_jump_sec:.0f} с/прыжок", "muted"))
    if state.session_scan_value:
        row.segments.append(Segment(f" · скан {values.credits(state.session_scan_value)}", "text"))
    if state.session_map_value:
        row.segments.append(Segment(f" · DSS {values.credits(state.session_map_value)}", "text"))
    if state.session_organic_estimate:
        row.segments.append(Segment(f" · био ≈{values.credits(state.session_organic_estimate)}", "ok"))
    if state.session_sold or state.session_organic_sold:
        total = state.session_sold + state.session_organic_sold
        row.segments.append(Segment(f" · продано {values.credits(total)}", "accent"))
    if state.status.low_fuel:
        row.segments.append(Segment("  МАЛО ТОПЛИВА", "bad"))
    return row


def build_view(
    state: GameState,
    cfg,
    expanded: bool | None = None,
    now: float | None = None,
    hint: str | None = None,
) -> HudView:
    now = now or time.time()
    route_row, progress, dots, accent = _route_row(state, cfg)
    body_row = _body_row(state, cfg)
    expanded = cfg.expanded if expanded is None else expanded
    detail = _detail_rows(state, cfg, now) if expanded else []
    alert = None
    if state.organic_alert and now - state.organic_alert_ts < 6:
        alert = state.organic_alert
    return HudView(
        route_row=route_row,
        body_row=body_row,
        detail=detail,
        progress=progress,
        dots=dots,
        alert=alert,
        accent=accent,
        hint=hint,
    )

# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:22:52
# Edited by nc.ai 1.2.11 on Papasha 2026-11-14 17:19:46
# Edited by nc.ai 1.2.15 on new-admin-pc 2026-11-17 16:12:08
"""Модель отображения HUD: из GameState в строки/сегменты для рендера.

Чистый слой без зависимостей от UI — его используют и tkinter-оверлей, и
терминальный режим, и тесты.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import bio, codex, values
from .i18n import jumps_word, t
from .model import FIRST_LOGGED_MULTIPLIER, Body, GameState, RadarView


@dataclass
class Segment:
    text: str
    style: str = "text"
    # Если задано — двойной клик по этому куску копирует имя системы, а не всю строку.
    copy: str | None = None

    def __post_init__(self) -> None:
        # журнал иногда отдаёт Body как int — не роняем "".join в plain()
        if not isinstance(self.text, str):
            self.text = "" if self.text is None else str(self.text)


@dataclass
class Row:
    segments: list[Segment] = field(default_factory=list)
    # правый хвост строки: рисуется целиком, даже если левая часть не влезает
    tail: list[Segment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(str(s.text) for s in self.segments + self.tail)


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


def _ls(value: float) -> str:
    if not value:
        return "—"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} {t('unit.million')} ls"
    if value >= 10_000:
        return f"{value / 1000:,.0f} {t('unit.thousand')} ls".replace(",", " ")
    return f"{value:,.0f} ls".replace(",", " ")


def _meters(value: float) -> str:
    return f"{value:,.0f} {t('unit.m')}".replace(",", " ")


def _genus_name_list(body: Body, limit: int = 4) -> list[str]:
    if not body.genuses:
        return []
    parts: list[str] = []
    items = list(body.genuses.items())
    for key, count in items[:limit]:
        name = codex.display_name(key)
        parts.append(f"{name}×{count}" if count > 1 else name)
    if len(items) > limit:
        parts.append(f"+{len(items) - limit}")
    return parts


def _genuses(body: Body, limit: int = 4) -> str:
    return ", ".join(_genus_name_list(body, limit=limit))


def _body_value_text(body: Body, odyssey: bool = True) -> tuple[str, str]:
    """(текст, стиль) цены картографии тела."""
    breakdown = values.body_values(body, odyssey=odyssey)
    if breakdown is None:
        return "", "muted"
    return values.credits(breakdown.mapped), "accent"


def _route_row(state: GameState, cfg) -> tuple[Row, tuple[int, int], list[bool], str]:
    route = state.route
    system = state.system.name
    row = Row()
    if not route.hops:
        row.segments.append(Segment(t("hud.route"), "dim"))
        if state.fsd_target:
            row.segments.append(Segment(state.fsd_target, "accent"))
            if state.jumps_in_route:
                row.segments.append(Segment(t("hud.jumps_short", n=state.jumps_in_route), "text"))
        else:
            row.segments.append(Segment(t("hud.route_unset"), "muted"))
        return row, (0, 0), [], "muted"

    done, total = route.progress(system)
    next_hop = route.next_hop(system)
    remaining = route.remaining(system)
    remaining_ly = route.distance_remaining(system, state.position)

    row.segments.append(Segment(t("hud.route"), "dim"))
    row.segments.append(Segment(f"{done}/{total}", "fg"))
    if next_hop:
        star = f"{next_hop.star_class}" if next_hop.star_class else "?"
        row.segments.append(Segment("  →  ", "muted"))
        row.segments.append(Segment(next_hop.system, "accent"))
        row.segments.append(Segment(f" ({star} · {_ly(next_hop.distance)} ly)", "muted"))
        if remaining:
            row.segments.append(Segment(t("hud.remaining"), "dim"))
            row.segments.append(
                Segment(f"{remaining} {jumps_word(remaining)} {t('hud.of')} {total}", "text")
            )
            if remaining_ly:
                row.segments.append(Segment(f" · {_ly(remaining_ly)} ly", "muted"))
        row.segments.append(Segment("  ", "text"))
        if next_hop.scoopable:
            row.segments.append(Segment(t("hud.scoop"), "ok"))
        else:
            row.segments.append(Segment(t("hud.no_scoop"), "warn"))
    else:
        row.segments.append(Segment(t("hud.finish"), "ok"))

    if route.locked:
        row.segments.append(Segment(t("hud.locked"), "warn"))

    dots_total = max(1, total)
    dots = [i < done for i in range(min(dots_total, 40))]
    accent = "fg" if remaining else "ok"
    return row, (done, total), dots, accent


def _body_kind_label(body) -> str:
    """Префикс строки: ЗВЕЗДА у звезды/прибытия, ТЕЛО у планеты."""
    if body is None:
        return t("hud.star_label")
    if body.is_star or body.star_type:
        return t("hud.star_label")
    return t("hud.body")


def _discovered_mark(state: GameState) -> Segment | None:
    """Золотая галочка: систему открыл текущий командир."""
    if state.system.discovered_by_me:
        return Segment(" ✔", "gold")
    return None


def _body_row(state: GameState, cfg) -> Row:
    row = Row()
    body = state.hud_focus_body()
    row.segments.append(Segment(_body_kind_label(body), "dim"))
    if body is None:
        name = state.system.name or "—"
        count = t("hud.bodies_n", n=state.system.body_count) if state.system.body_count else ""
        row.segments.append(Segment(f"{name}{count}", "muted"))
        mark = _discovered_mark(state)
        if mark is not None:
            row.segments.append(mark)
        return row

    body_class = body.planet_class or body.star_type or (t("hud.star") if body.is_star else "?")
    row.segments.append(Segment(body.name, "fg"))
    row.segments.append(Segment(f" · {body_class}", "muted"))
    if body.distance_ls:
        row.segments.append(Segment(f" · {_ls(body.distance_ls)}", "muted"))
    if body.is_star or body.star_type:
        mark = _discovered_mark(state)
        if mark is not None:
            row.segments.append(mark)

    # звезда / газовый гигант — без БИО; в прыжке био текущего тела тоже не нужно
    no_bio = bool(body.is_star or body.star_type) or "gas giant" in (body.planet_class or "").lower()
    bio_off = bool(getattr(state, "jumping_away", False)) or no_bio
    if not bio_off:
        row.segments.append(Segment(t("hud.bio"), "dim"))
        # Чужой счётчик (EDSM/Spansh/EDDN) на HUD не показываем, пока не включена настройка.
        # Свои сигналы журнала и таблица Bodies от этого не зависят.
        if not _bio_visible_on_hud(body, cfg) or (body.bio_signals is None and not body.signals_known):
            row.segments.append(Segment("?", "muted"))
        elif not body.bio_signals:
            row.segments.append(Segment("0", "muted"))
        else:
            row.segments.append(Segment(str(body.bio_signals), "ok"))
            forecast = bio.forecast_names(body, state.system, limit=3)
            if forecast:
                row.segments.append(Segment(f" ({', '.join(forecast)})", "muted"))
            else:
                genuses = _genuses(body)
                if genuses:
                    row.segments.append(Segment(f" ({genuses})", "muted"))
    if body.geo_signals:
        row.segments.append(Segment(t("hud.geo", n=body.geo_signals), "muted"))

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
        row.segments.append(Segment(t("hud.samples"), "dim"))
        row.segments.append(Segment(f"{organic.genus_en} {organic.scans_text}", "warn"))
        colony = state.colony_distance()
        if colony:
            dist, need = colony
            style = "bad" if dist < need else "ok"
            row.segments.append(Segment(t("hud.colony", dist=_meters(dist), need=need), style))

    if state.status.srv:
        row.segments.append(Segment("   [SRV]", "accent"))
    elif state.mode == "OnFoot":
        row.segments.append(Segment(t("hud.on_foot"), "accent"))
    if state.legacy:
        row.segments.append(Segment("   [Legacy 3.8]", "warn"))
    return row


def _guide_turn(turn: float | None) -> str:
    if turn is None:
        return ""
    if abs(turn) <= 12:
        return "  ▲"
    arrow = "▶" if turn > 0 else "◀"
    return f"  {arrow} {abs(turn):.0f}°"


def _guide_dist(meters: float) -> str:
    if meters >= 10_000:
        return f"{meters / 1000:.1f} {t('unit.km')}"
    return f"{meters:,.0f} {t('unit.m')}".replace(",", " ")


def _sample_rows(state: GameState) -> list[Row]:
    """Прогресс проб + колония + ближайший образец (и после рестарта игры/EDHUD)."""
    from . import codex

    organic = state.active_organic()
    if organic is None:
        return []
    need = codex.sample_range(organic.genus)
    rows: list[Row] = []
    head = Row(
        [
            Segment(t("hud.sample_head", genus=organic.genus_en, scans=organic.scans_text), "warn"),
            Segment(t("hud.interval", need=need), "dim"),
        ]
    )
    colony = state.colony_distance()
    if colony is not None:
        dist, need_m = colony
        if dist >= need_m:
            head.segments.append(Segment(t("hud.next_sample"), "ok"))
        else:
            gap = max(0.0, need_m - dist)
            head.segments.append(
                Segment(
                    t("hud.from_prev", dist=_guide_dist(dist), gap=_guide_dist(gap)),
                    "bad",
                )
            )
    elif organic.samples_done > 0 and not organic.sample_pos:
        head.segments.append(Segment(t("hud.no_sample_pos"), "dim"))
    rows.append(head)

    plan = state.sample_plan()
    if plan is None:
        return rows
    for guide in plan.guides:
        if guide.kind == "away":
            course = f"{guide.bearing:.0f}°" if guide.bearing is not None else "—"
            text = (
                t("hud.step_away", dist=_guide_dist(guide.distance_m), course=course)
                + _guide_turn(guide.turn)
            )
            rows.append(Row([Segment("  ", "dim"), Segment(text, "warn")]))
            continue
        if guide.kind == "spot":
            course = t("hud.bearing", deg=f"{guide.bearing:.0f}") if guide.bearing is not None else ""
            rows.append(
                Row(
                    [
                        Segment(t("hud.nearest"), "accent"),
                        Segment(str(guide.title), "text"),
                        Segment(f"  {_guide_dist(guide.distance_m)}{course}{_guide_turn(guide.turn)}", "ok"),
                    ]
                )
            )
            continue
        style = "ok" if guide.ready else "bad"
        mark = t("hud.enough") if guide.ready else t("hud.close")
        course = t("hud.bearing", deg=f"{guide.bearing:.0f}") if guide.bearing is not None else ""
        rows.append(
            Row(
                [
                    Segment(f"  {guide.title}  ", "text"),
                    Segment(t("hud.need_m", dist=_guide_dist(guide.distance_m), need=guide.need_m), style),
                    Segment(f"{course}{_guide_turn(guide.turn)}  {mark}", style),
                ]
            )
        )
    return rows


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
    row = Row([Segment(t("hud.value"), "dim")])
    row.segments.append(Segment(t("hud.scan", value=values.credits(breakdown.scan)), "text"))
    row.segments.append(Segment(t("hud.with_dss", value=values.credits(breakdown.mapped)), "text"))
    if breakdown.first_discoverer:
        row.segments.append(Segment(t("hud.first_disc", mult=values.DISCOVERY_MULTIPLIER), "ok"))
    elif breakdown.first_mapper:
        row.segments.append(Segment(t("hud.first_map"), "ok"))
    if body.landable:
        if body.was_footfalled:
            row.segments.append(Segment(t("hud.foot_done"), "muted"))
        else:
            row.segments.append(Segment(t("hud.foot_chance"), "ok"))
    if body.discovered_by:
        row.segments.append(Segment(t("hud.discovered_by", name=body.discovered_by), "muted"))
    if body.mapped_by:
        row.segments.append(Segment(t("hud.mapped_by", name=body.mapped_by), "muted"))
    return row


def _mining_row(state: GameState) -> Row | None:
    """Строка добычи в верхнем HUD: качество камня и выработка за сессию."""
    metrics = getattr(state, "mining", None)
    if metrics is None or not metrics.has_data():
        return None
    text = metrics.hud_text()
    if not text:
        return None
    row = Row()
    row.segments.append(Segment(t("hud.mining"), "muted"))
    row.segments.append(Segment(text, "text"))
    return row


def _detail_rows(state: GameState, cfg, now: float) -> list[Row]:
    rows: list[Row] = []
    body = state.hud_focus_body()
    max_pred = max(1, int(cfg.max_predictions))
    # прыгаем в другую систему — всё про био этой системы из дашборда убираем
    bio_off = bool(getattr(state, "jumping_away", False))

    if body is not None:
        if not bio_off:
            rows.extend(_organism_rows(state, body))
        value_row = _value_row(state, body)
        if value_row is not None:
            rows.append(value_row)

    if (
        body is not None
        and not bio_off
        and cfg.show_predictions
        and state.odyssey
        and (body.landable or body.genuses)
    ):
        predictions = bio.predict_for_body(body, state.system, limit=max_pred)
        if predictions:
            head = Row([Segment(t("hud.predict"), "dim")])
            head.segments.append(Segment(", ".join(sorted({p.genus for p in predictions})), "accent"))
            rows.append(head)
            for prediction in predictions[:max_pred]:
                row = Row([Segment("≈ ", "muted"), Segment(prediction.label, "text")])
                if prediction.reward:
                    row.segments.append(Segment(f"  {values.credits(prediction.reward)}", "muted"))
                rows.append(row)

    system_bio = []
    if not bio_off:
        system_bio = [
            b for b in state.system.bio_bodies if b is not body and _bio_visible_on_hud(b, cfg)
        ]
    if system_bio:
        head = Row([Segment(t("hud.bio_in_system"), "dim")])
        head.segments.append(Segment(f"{len(system_bio)}", "ok"))
        rows.append(head)
        for candidate in sorted(system_bio, key=lambda b: b.distance_ls)[:6]:
            row = Row([Segment("• ", "muted"), Segment(candidate.name, "text")])
            row.segments.append(Segment(t("hud.signals", n=candidate.bio_signals), "ok"))
            forecast = bio.forecast_names(candidate, state.system, limit=3)
            if forecast:
                prefix = "  ≈ " if not candidate.genuses else "  "
                row.segments.append(Segment(f"{prefix}{', '.join(forecast)}", "accent" if not candidate.genuses else "muted"))
            else:
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


def _carrier_who(carrier) -> str:
    who = (carrier.callsign or carrier.name or "").strip()
    low = who.lower().replace("ё", "е")
    if not who or low in {"карриер", "carrier", "fleet carrier"} or low.replace(" ", "") in {
        "карриеркарриер",
        "carriercarrier",
    }:
        return t("hud.carrier")
    return who


def _carrier_context(state: GameState) -> tuple[str, str] | None:
    carrier = state.carrier
    if not carrier.known:
        return None
    who = _carrier_who(carrier)
    generic = t("hud.carrier")
    prefix = generic if who.lower() == generic.lower() else f"{generic} {who}"
    where = carrier.system or "—"
    return prefix, where


def _carrier_segments(state: GameState) -> list[Segment]:
    ctx = _carrier_context(state)
    if ctx is None:
        return []
    prefix, where = ctx
    carrier = state.carrier
    if carrier.jump_pending and carrier.jump_dest_system:
        frm = carrier.jump_from_system or where
        dest = carrier.jump_dest_system
        return [
            Segment(t("hud.carrier_prep_head", prefix=prefix), "accent"),
            Segment(frm, "warn", copy=None if frm == "—" else frm),
            Segment(t("hud.carrier_prep_arrow"), "accent"),
            Segment(dest, "warn", copy=dest),
        ]
    dist = state.carrier_distance_ly()
    if dist is None:
        if state.carrier_pos_pending:
            label = t("hud.carrier_seek", prefix=prefix, where=where)
        else:
            label = t("hud.carrier_at", prefix=prefix, where=where)
    elif dist < 0.05:
        label = t("hud.carrier_here", prefix=prefix, where=where)
    else:
        text = f"{dist:,.1f}".replace(",", " ")
        key = "hud.carrier_dist_approx" if state.carrier_distance_is_approx() else "hud.carrier_dist"
        label = t(key, prefix=prefix, where=where, dist=text)
    copy = None if where == "—" else where
    return [Segment(label, "accent", copy=copy)]


def _carrier_label(state: GameState) -> str | None:
    parts = _carrier_segments(state)
    if not parts:
        return None
    return "".join(part.text for part in parts)


def _carrier_row(state: GameState) -> Row | None:
    """Отдельная 3-я строка дашборда: место карриера / ly / подготовка к прыжку."""
    parts = _carrier_segments(state)
    if not parts:
        return None
    return Row(list(parts))


def _system_row(state: GameState) -> Row:
    system = state.system
    scan_sum, mapped_sum = values.system_totals(system, odyssey=state.odyssey)
    row = Row([Segment(t("hud.system"), "dim")])
    if system.name:
        row.segments.append(Segment(system.name, "fg"))
        row.segments.append(Segment(" · ", "muted"))
    if system.discovered_by_me:
        name = (getattr(state, "cmdr", None) or "").strip()
        label = t("route.your_discovery_named", name=name) if name else t("hud.opened_by_you")
        row.segments.append(Segment(label, "gold"))
        row.segments.append(Segment(" · ", "muted"))
    row.segments.append(Segment(t("hud.n_bodies", n=len(system.bodies)), "text"))
    if scan_sum:
        row.segments.append(Segment(t("hud.data", value=values.credits(scan_sum)), "text"))
        row.segments.append(Segment(t("hud.dss_sum", value=values.credits(mapped_sum)), "text"))
    if system.remote_scan_value:
        label = f" · EDSM ≈{values.credits(system.remote_scan_value)}"
        if system.remote_mapped_value:
            label += t("hud.edsm_maps", value=values.credits(system.remote_mapped_value))
        row.segments.append(Segment(label, "accent"))
    if system.remote_sources:
        row.segments.append(Segment(t("hud.remote", sources=", ".join(system.remote_sources)), "muted"))
    if state.legacy:
        row.segments.append(Segment(t("hud.legacy"), "warn"))
    return row


def _session_row(state: GameState) -> Row:
    row = Row([Segment(t("hud.session"), "dim")])
    row.segments.append(Segment(t("hud.session_jumps", n=state.session_jumps), "text"))
    fresh = "ok" if state.session_new_systems else "text"
    row.segments.append(Segment(t("hud.new_systems", n=state.session_new_systems), fresh))
    if state.avg_jump_sec >= 10:
        row.segments.append(Segment(t("hud.sec_jump", n=state.avg_jump_sec), "muted"))
    if state.session_scan_value:
        row.segments.append(Segment(t("hud.sess_scan", value=values.credits(state.session_scan_value)), "text"))
    if state.session_map_value:
        row.segments.append(Segment(t("hud.sess_dss", value=values.credits(state.session_map_value)), "text"))
    if state.session_organic_estimate and not getattr(state, "jumping_away", False):
        row.segments.append(Segment(t("hud.sess_bio", value=values.credits(state.session_organic_estimate)), "ok"))
    if state.session_sold or state.session_organic_sold:
        total = state.session_sold + state.session_organic_sold
        row.segments.append(Segment(t("hud.sold", value=values.credits(total)), "accent"))
    if state.status.low_fuel:
        row.segments.append(Segment(t("hud.low_fuel"), "bad"))
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
    detail: list[Row] = []
    # 3-я строка: карриер (место / ly / подготовка к прыжку) — всегда, если известен
    carrier_row = _carrier_row(state)
    if carrier_row is not None:
        detail.append(carrier_row)
    # «Показывать маршрут и статистику» выключено — остаются маршрут, тело и карриер
    if getattr(cfg, "hud_show_stats", True):
        detail.extend(_sample_rows(state))
        mining_row = _mining_row(state)
        if mining_row is not None:
            detail.append(mining_row)
        if expanded:
            detail.extend(_detail_rows(state, cfg, now))
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


# ------------------------------------------------------- левая панель биологии
# Как PlotBioSystem у SrvSurvey: после своего FSS список находок слева.
# В сканере и у выбранного тела — виды этой планеты, иначе сводка по системе.

_BAR_EDGES = (3_000_000, 7_000_000, 12_000_000)


@dataclass
class BioLine:
    segments: list[Segment] = field(default_factory=list)
    tail: list[Segment] = field(default_factory=list)
    bars: int = 0
    bars_max: int = 0
    rule: bool = False

    @property
    def text(self) -> str:
        head = "".join(segment.text for segment in self.segments)
        tail = "".join(segment.text for segment in self.tail)
        # хвост (цена) в текстовом виде отделяем от имени: в оверлее он
        # выравнивается по правому краю, а в TUI/логах иначе слипается
        return f"{head}  {tail}" if tail else head


@dataclass
class BioBoard:
    title: str
    lines: list[BioLine] = field(default_factory=list)
    footers: list[tuple[str, str]] = field(default_factory=list)
    radar: RadarView | None = None

    def plain(self) -> list[str]:
        lines = [self.title] + [line.text for line in self.lines]
        lines.extend(text for text, _style in self.footers)
        if self.radar is not None:
            lines.append(
                f"radar:{self.radar.range_m:.0f}:{self.radar.need_m}:{self.radar.ready}:"
                f"{self.radar.heading if self.radar.heading is not None else '-'}"
            )
            for blip in self.radar.blips:
                lines.append(
                    f"{blip.kind}:{blip.distance_m:.0f}:{blip.bearing:.0f}:"
                    f"{blip.ready}:{blip.index}:{blip.label}"
                )
        return lines


def _short_body(body: Body, system) -> str:
    name = (body.name or "").strip()
    system_name = (system.name or "").strip()
    if system_name and name.lower().startswith(system_name.lower()):
        rest = name[len(system_name):].strip(" -")
        if rest:
            return rest
    return name or "?"


def _reward_bars(value: int) -> int:
    if value <= 0:
        return 0
    bars = 1
    for edge in _BAR_EDGES:
        if value > edge:
            bars += 1
    return bars


def _credit_span(low: int, high: int) -> str:
    if not low and not high:
        return "—"
    if not high or low == high:
        return values.credits(low or high)
    return f"{values.credits(low)}–{values.credits(high)}"


def _bio_visible_on_hud(body: Body, cfg) -> bool:
    """Био на верхнем HUD: своё из журнала всегда, чужое — только по настройке."""
    if body.signals_local or body.organisms:
        return True
    return bool(getattr(cfg, "show_remote_bio", False))


def _own_bio_bodies(state: GameState) -> list[Body]:
    bodies = [
        body
        for body in state.system.bodies.values()
        if (body.bio_signals or 0) > 0 and body.signals_local
    ]
    return sorted(bodies, key=lambda body: body.body_id)


def _player_body(state: GameState) -> Body | None:
    """Тело, на котором командир реально «сидит» (посадка / SRV / пешком / атмосфера).

    Одних Latitude/BodyID мало: они есть в орбитальном круизе и при наведении
    цели. Иначе после снятия цели панель био так и остаётся на одной планете.
    """
    status = state.status
    body = state.system.bodies.get(status.body_id) if status.body_id is not None else None
    if body is None:
        name = (status.body_name or "").strip().lower()
        if name:
            for candidate in state.system.bodies.values():
                if (candidate.name or "").strip().lower() == name:
                    body = candidate
                    break
    if body is None:
        return None
    if status.landed or status.srv or status.glide or state.mode == "OnFoot":
        return body
    if state.in_atmosphere and status.has_lat_long:
        return body
    return None


def _has_bio(body: Body) -> bool:
    return bool(body.bio_signals or body.genuses or body.organisms)


def _destination_bio_body(state: GameState, own: dict[int, Body]) -> Body | None:
    """Лок именно био-планеты. Лок звезды (Body 0) / системы → None → сводка всех био."""
    status = state.status
    body_id = status.destination_body
    if body_id is None or body_id == 0:
        return None
    body = own.get(body_id)
    if body is None:
        return None
    if body.is_star or body.star_type:
        return None
    return body


def _hard_on_body(state: GameState) -> bool:
    status = state.status
    return bool(status.landed or status.srv or status.glide or state.mode == "OnFoot")


def _focus_bio_body(state: GameState) -> Body | None:
    """Планета, чьи виды показывать вместо сводки системы.

    Одна планета только если:
    • реально на поверхности (посадка / SRV / пешком / глид), или
    • залочена био-планета (Destination.Body ≠ 0), или
    • открыт FSS (GuiFocus 9) и выбрана карточка тела.

    Лок звезды (Body 0) / снятие лока / взлёт → все био системы.
    """
    status = state.status
    force_system = getattr(state, "bio_force_system", False)
    own = {body.body_id: body for body in _own_bio_bodies(state)}

    # поверхность — всегда карточка этой планеты (или None, если без био)
    if _hard_on_body(state):
        here = _player_body(state)
        if here is not None:
            return here if _has_bio(here) else None

    if not own:
        return None

    # лок звезды / системы → сводка (не держим «атмосферную» карточку)
    if status.destination_body == 0:
        return None

    # после взлёта игнорируем залипший Destination на старой планете
    if force_system:
        if status.gui_focus == 9:
            last = own.get(state.last_fss_body_id or -1)
            if last is not None:
                return last
        return None

    locked = _destination_bio_body(state, own)
    if locked is not None:
        return locked

    # мягкий «на теле» (атмосфера + lat) — только без лока звезды и без force
    here = _player_body(state)
    if here is not None:
        return here if _has_bio(here) else None

    if status.gui_focus == 9:
        last = own.get(state.last_fss_body_id or -1)
        if last is not None:
            return last
    return None


def _prediction_groups(body: Body, state: GameState) -> list[tuple[str, list[tuple[str, list[str], int]]]]:
    predictions = bio.predict_for_body(body, state.system, limit=64)
    grouped: dict[str, dict[str, dict]] = {}
    order: list[str] = []
    for prediction in predictions:
        if prediction.genus not in grouped:
            grouped[prediction.genus] = {}
            order.append(prediction.genus)
        species = grouped[prediction.genus].setdefault(
            prediction.species, {"variants": [], "reward": prediction.reward}
        )
        if prediction.variant and prediction.variant not in species["variants"]:
            species["variants"].append(prediction.variant)
        if prediction.reward and not species["reward"]:
            species["reward"] = prediction.reward
    result: list[tuple[str, list[tuple[str, list[str], int]]]] = []
    for genus in order:
        species_rows = [
            (species, info["variants"], int(info["reward"] or 0))
            for species, info in grouped[genus].items()
        ]
        result.append((genus, species_rows))
    if body.genuses:
        # род из DSS показываем всегда, даже если критерии не дали ни одного вида
        covered = {genus.lower().rstrip("s") for genus in order}
        for key in body.genuses:
            name = codex.display_name(key)
            if name.lower().rstrip("s") in covered:
                continue
            result.append((name, []))
            covered.add(name.lower().rstrip("s"))
    return result


def _genus_span(species_rows: list[tuple[str, list[str], int]]) -> tuple[int, int]:
    rewards = [reward for _species, _variants, reward in species_rows if reward]
    if not rewards:
        return 0, 0
    return min(rewards), max(rewards)


def _sampled_genera(body: Body) -> set[str]:
    return {(organic.genus_en or "").lower() for organic in body.organisms.values() if organic.genus_en}


def _bio_complete(body: Body) -> bool:
    """Все биосигналы планеты уже проанализированы (взяты)."""
    need = body.bio_signals or 0
    return need > 0 and body.bio_analysed >= need


def _ff_taken(body: Body) -> bool:
    """Первый шаг уже не свободен: журнал WasFootfalled или мы сами брали пробы."""
    if body.was_footfalled:
        return True
    return any(organic.samples > 0 or organic.analysed for organic in body.organisms.values())


def _body_reward_span(body: Body, state: GameState) -> tuple[int, int]:
    """Сумма награды: точные payout взятых организмов + вилка только по ещё не взятым родам."""
    exact = sum(organic.payout for organic in body.organisms.values() if organic.payout)
    if _bio_complete(body) and exact:
        return exact, exact

    sampled = _sampled_genera(body)
    pred_low = 0
    pred_high = 0
    for genus, species_rows in _prediction_groups(body, state):
        if genus.lower() in sampled:
            continue
        low, high = _genus_span(species_rows)
        if low or high:
            pred_low += low
            pred_high += high

    if exact or pred_low or pred_high:
        return exact + pred_low, exact + pred_high
    return 0, 0


def _body_lines(body: Body, state: GameState) -> tuple[list[BioLine], tuple[int, int]]:
    lines: list[BioLine] = []
    sampled = _sampled_genera(body)
    for organic in sorted(body.organisms.values(), key=lambda item: item.label):
        style = "ok" if organic.analysed else "warn"
        reward = organic.payout
        lines.append(
            BioLine(
                segments=[
                    Segment(organic.label, style),
                    Segment(f"  {organic.scans_text}", style),
                ],
                tail=[Segment(values.credits(reward) if reward else "—", "muted")],
                bars=_reward_bars(reward),
            )
        )
    # всё взято — предсказания «?» больше не показываем (ни в сводке, ни в карточке)
    groups = [] if _bio_complete(body) else _prediction_groups(body, state)
    block = 0
    for genus, species_rows in groups:
        if genus.lower() in sampled:
            continue
        if not species_rows:
            # вид не предсказан — показываем хотя бы род из DSS
            lines.append(
                BioLine(
                    segments=[Segment("? ", "accent"), Segment(genus, "accent")],
                    rule=block > 0,
                )
            )
            block += 1
            continue
        low, high = _genus_span(species_rows)
        for index, (species, variants, reward) in enumerate(species_rows):
            phrase = bio.species_label(genus, species)
            if len(variants) == 1:
                text = f"{phrase} - {variants[0]}"
            elif variants:
                text = f"{phrase}: {', '.join(variants)}"
            else:
                text = phrase
            lines.append(
                BioLine(
                    segments=[
                        Segment("? ", "accent"),
                        Segment(text, "accent"),
                    ],
                    tail=[Segment(values.credits(reward) if reward else "—", "muted")],
                    bars=_reward_bars(reward),
                    rule=block > 0 and index == 0,
                )
            )
        # несколько видов одного рода — строка-итог с вилкой цены (как PlotBioSystem)
        if len(species_rows) > 1:
            lines.append(
                BioLine(
                    segments=[Segment(genus, "fg")],
                    tail=[Segment(_credit_span(low, high), "muted")],
                    bars=_reward_bars(low),
                    bars_max=_reward_bars(high),
                )
            )
        block += 1
    if not lines and body.genuses:
        for key in body.genuses:
            lines.append(BioLine(segments=[Segment(codex.display_name(key), "ok")]))
    elif not groups and not body.organisms and not body.genuses:
        note = t("hud.no_species") if body.planet_class else t("hud.no_scan")
        lines.append(BioLine(segments=[Segment(note, "dim")]))
    low, high = _body_reward_span(body, state)
    return lines, (low, high)


def _ff_segment(body: Body) -> Segment | None:
    """Метка первого шага: «FF+» свободен, «FF» уже занят (журнал или наши пробы).

    Бонус за первый шаг входит в «с первым шагом» внизу панели, но по одной
    планете не видно, свободен ли он: метка отвечает на этот вопрос сразу.
    """
    if _ff_taken(body):
        return Segment(t("hud.ff_taken"), "muted")
    if getattr(body, "landable", False):
        return Segment(t("hud.ff_free"), "ok")
    return None


def _ff_bonus_open(body: Body) -> bool:
    """Показывать вилку «футфол ×5» только пока шаг свободен и био ещё не закрыто."""
    return bool(body.landable) and not _ff_taken(body) and not _bio_complete(body)


def _ff_legend(bodies) -> tuple[str, str] | None:
    """Сноска к меткам — только пока хоть у одной планеты шаг ещё свободен (FF+)."""
    landable = [body for body in bodies or [] if getattr(body, "landable", False)]
    if not landable:
        return None
    if not any(not _ff_taken(body) for body in landable):
        return None
    return (t("hud.ff_legend"), "dim")


def _system_lines(state: GameState) -> tuple[list[BioLine], tuple[int, int], tuple[int, int]]:
    """Сводка по системе: на каждый сигнал — своя цена, под ними итог планеты."""
    lines: list[BioLine] = []
    total_low = 0
    total_high = 0
    ff_low = 0
    ff_high = 0
    for body_index, body in enumerate(_own_bio_bodies(state)):
        body_lines, (low, high) = _body_lines(body, state)
        total_low += low
        total_high += high
        if _ff_bonus_open(body):
            ff_low += int(round(low * FIRST_LOGGED_MULTIPLIER))
            ff_high += int(round(high * FIRST_LOGGED_MULTIPLIER))
        else:
            ff_low += low
            ff_high += high
        done = _bio_complete(body)
        highlight = _marked(body, state)
        style = "muted" if done else ("accent" if highlight else "text")
        # шапка планеты: имя, число сигналов и расстояние — цена ушла к сигналам
        header_segments = [
            Segment(_short_body(body, state.system), style),
            Segment(f"  ×{body.bio_signals}", "muted" if done else "ok"),
        ]
        ff_segment = _ff_segment(body)
        if ff_segment is not None:
            header_segments.append(Segment("  ", "dim"))
            header_segments.append(ff_segment)
        lines.append(
            BioLine(
                segments=header_segments,
                tail=[Segment(_ls(body.distance_ls), "dim")],
                rule=body_index > 0,
            )
        )
        lines.extend(_mute_lines(body_lines) if done else body_lines)
        if low or high:
            lines.append(
                BioLine(
                    segments=[Segment(f"  {t('hud.body_total')}", "dim")],
                    tail=[Segment(_credit_span(low, high), "fg")],
                )
            )
    return lines, (total_low, total_high), (ff_low, ff_high)


def _mute_lines(lines: list[BioLine]) -> list[BioLine]:
    """Сданная планета — всё её строки приглушаем, как было до правки."""
    muted: list[BioLine] = []
    for line in lines:
        muted.append(
            BioLine(
                segments=[Segment(segment.text, "muted", copy=segment.copy) for segment in line.segments],
                tail=[Segment(segment.text, "muted", copy=segment.copy) for segment in line.tail],
                bars=line.bars,
                bars_max=line.bars_max,
                rule=line.rule,
            )
        )
    return muted


def _marked(body: Body, state: GameState) -> bool:
    status = state.status
    if status.body_id == body.body_id or status.destination_body == body.body_id:
        return True
    dest = (status.destination_name or "").strip().lower()
    if not dest:
        return False
    return dest in {_short_body(body, state.system).lower(), (body.name or "").lower()}


def _footers(low: int, high: int, ff_low: int, ff_high: int, with_bonus: bool) -> list[tuple[str, str]]:
    footers = [(t("hud.total", value=_credit_span(low, high)), "fg")]
    if with_bonus and (ff_low or ff_high) and (ff_low != low or ff_high != high):
        footers.append((t("hud.footfall", value=_credit_span(ff_low, ff_high)), "accent"))
    return footers


def build_bio_board(state: GameState) -> BioBoard | None:
    """Левый дашборд биологии. Пусто, пока командир сам не снял биосигналы.

    На прыжке в другую систему окно закрывается и снова появляется после FSS,
    если в новой системе есть биология.
    """
    if state.bio_panel_suppressed():
        return None
    focus = _focus_bio_body(state)
    # после взлёта / лока звезды player_body может ещё «залипать» — сводку не прячем
    if focus is None and _player_body(state) is not None:
        force = getattr(state, "bio_force_system", False)
        star_lock = state.status.destination_body == 0
        if not force and not star_lock:
            # стоим на теле без биологии: сводку системы здесь не показываем
            return None
    bodies = _own_bio_bodies(state)
    if not bodies and focus is None:
        return None
    radar = state.radar_view()
    if focus is not None:
        lines, (low, high) = _body_lines(focus, state)
        if state.status.body_id == focus.body_id:
            extra = [
                BioLine(segments=list(row.segments), tail=list(row.tail))
                for row in _sample_rows(state)
            ]
            lines = extra + lines
        bonus = _ff_bonus_open(focus)
        ff_low = low * FIRST_LOGGED_MULTIPLIER if bonus else low
        ff_high = high * FIRST_LOGGED_MULTIPLIER if bonus else high
        count = focus.bio_signals or 0
        title = t("hud.body_bio", name=_short_body(focus, state.system), n=count)
        ff_segment = _ff_segment(focus)
        if ff_segment is not None:
            title = f"{title}  {ff_segment.text}"
        footers = _footers(low, high, ff_low, ff_high, bonus)
        legend = _ff_legend([focus])
        if legend is not None:
            footers = footers + [legend]
        return BioBoard(
            title=title,
            lines=lines,
            footers=footers,
            radar=radar,
        )
    lines, (low, high), (ff_low, ff_high) = _system_lines(state)
    total = sum(body.bio_signals or 0 for body in bodies)
    bonus = any(_ff_bonus_open(body) for body in bodies)
    footers = _footers(low, high, ff_low, ff_high, bonus)
    legend = _ff_legend(bodies)
    if legend is not None:
        footers = footers + [legend]
    return BioBoard(
        title=t("hud.bio_title", n=total),
        lines=lines,
        footers=footers,
        radar=radar,
    )

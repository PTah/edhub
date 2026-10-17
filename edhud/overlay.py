# Edited by nc.ai 0.8.8.0 on macbook 2026-10-17 20:13:05
"""Оверлей в верхней части экрана (стиль SrvSurvey) на tkinter.

Свойства, которые нам нужны от окна:
  * без рамки и заголовка, всегда сверху (overrideredirect + topmost);
  * «сквозной» для мыши на Windows (WS_EX_TRANSPARENT|WS_EX_NOACTIVATE),
    чтобы клики уходили в игру (как в SrvSurvey plotters/PlotBase.cs);
  * полупрозрачность настраивается, F8 разворачивает панель подробностей,
    F9 включает/выключает сквозной режим, F10 прячет/показывает оверлей,
    F12 / ПКМ-меню / кнопка × — выход.
"""
from __future__ import annotations

import queue
import webbrowser

from . import winapi
from .hudmodel import HudView

PAD = 12
BAR_H = 4
CLOSE_SIZE = 18


class Overlay:
    def __init__(
        self,
        cfg,
        on_expanded=None,
        on_click_through=None,
        on_visible=None,
        on_quit=None,
        on_settings=None,
        system_name_provider=None,
        system_address_provider=None,
    ) -> None:
        import tkinter as tk
        from tkinter import font as tkfont

        self.tk = tk
        self.cfg = cfg
        self.on_expanded = on_expanded
        self.on_click_through = on_click_through
        self.on_visible = on_visible
        self.on_quit = on_quit
        self.on_settings = on_settings
        self.system_name_provider = system_name_provider
        self.system_address_provider = system_address_provider
        self._fonts: dict[tuple[int, bool], tkfont.Font] = {}
        self._view: HudView | None = None
        self._queue: queue.Queue = queue.Queue(maxsize=2)
        self._visible = True
        self._height = 66
        self._x = 0
        self._y = 0
        self._drag: tuple[int, int] | None = None
        self._last_draw = 0.0
        self.fullscreen: bool | None = None
        self._keeper: winapi.TopmostKeeper | None = None
        self._menu = None

        self.root = tk.Tk()
        self.root.title("EDHUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._request_quit)
        try:
            self.root.attributes("-alpha", max(0.25, min(1.0, float(cfg.opacity))))
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0, bg=cfg.color("panel"))
        self.canvas.pack(fill="both", expand=True)
        self._place_window()
        self._bind_keys()
        self._build_menu()
        self._apply_click_through()
        self._start_keeper()

    def _start_keeper(self) -> None:
        """Держим окно поверх всех и следим за полноэкранным режимом игры."""
        if not winapi.IS_WINDOWS or not getattr(self.cfg, "keep_topmost", True):
            return
        self._keeper = winapi.TopmostKeeper(
            hwnd_provider=lambda: winapi.hwnd_of(self.root),
            interval=2.0,
            on_fullscreen=self._on_fullscreen,
        )
        self._keeper.start()

    def _on_fullscreen(self, state: bool | None) -> None:
        self.fullscreen = state

    def _apply_click_through(self) -> None:
        hwnd = winapi.hwnd_of(self.root)
        winapi.apply_overlay_styles(
            hwnd,
            click_through=bool(self.cfg.click_through),
            topmost=bool(getattr(self.cfg, "keep_topmost", True)),
        )

    # ------------------------------------------------------------------ окно
    def _font(self, delta: int = 0, bold: bool = False):
        key = (delta, bold)
        if key not in self._fonts:
            from tkinter import font as tkfont

            family = self.cfg.font_family
            available = set(tkfont.families(self.root))
            for candidate in (family, "Consolas", "Cascadia Mono", "Segoe UI", "Menlo", "DejaVu Sans Mono"):
                if candidate in available:
                    family = candidate
                    break
            self._fonts[key] = tkfont.Font(
                family=family,
                size=max(7, int(self.cfg.font_size + delta)),
                weight="bold" if bold else "normal",
            )
        return self._fonts[key]

    def _place_window(self) -> None:
        width = int(self.cfg.width)
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = int((screen_w - width) / 2)
        y = int(self.cfg.top_offset)
        if getattr(self.cfg, "overlay_x", None) is not None:
            x = int(self.cfg.overlay_x)
        if getattr(self.cfg, "overlay_y", None) is not None:
            y = int(self.cfg.overlay_y)
        x = max(0, min(x, screen_w - 200))
        y = max(0, min(y, screen_h - 80))
        self._x, self._y = x, y
        self.root.geometry(f"{width}x{self._height}+{x}+{y}")

    def _resize(self, height: int) -> None:
        if abs(height - self._height) < 2:
            return
        self._height = height
        self.root.geometry(f"{int(self.cfg.width)}x{height}+{self._x}+{self._y}")

    def _bind_keys(self) -> None:
        self.root.bind("<F8>", lambda _e: self._toggle_expanded())
        self.root.bind("<F9>", lambda _e: self._toggle_click_through())
        self.root.bind("<F10>", lambda _e: self._toggle_visible())
        self.root.bind("<F12>", lambda _e: self._request_quit())
        self.canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<Button-3>", self._show_menu)

    def _build_menu(self) -> None:
        menu = self.tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Подробности (F8)", command=self._toggle_expanded)
        menu.add_command(label="Сквозной режим мыши (F9)", command=self._toggle_click_through)
        menu.add_command(label="Скрыть оверлей (F10)", command=self._toggle_visible)
        menu.add_separator()
        menu.add_command(label="Открыть систему на Spansh…", command=self._open_spansh)
        menu.add_command(label="Настройки…", command=self._open_settings)
        menu.add_separator()
        menu.add_command(label="Выход (F12)", command=self._request_quit)
        self._menu = menu

    def _show_menu(self, event) -> None:
        if self.cfg.click_through or self._menu is None:
            return
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _request_quit(self) -> None:
        if self.on_quit:
            self.on_quit()
        else:
            self.destroy()

    def _open_settings(self) -> None:
        if self.on_settings:
            self.on_settings()

    def _open_spansh(self) -> None:
        address = self.system_address_provider() if self.system_address_provider else None
        name = self.system_name_provider() if self.system_name_provider else None
        if address:
            url = f"https://spansh.co.uk/system/{int(address)}"
        elif name:
            from urllib.parse import quote

            url = f"https://spansh.co.uk/system/{quote(str(name))}"
        else:
            url = "https://spansh.co.uk/"
        webbrowser.open(url)

    def _toggle_expanded(self) -> None:
        (self.on_expanded or self.toggle_expanded)()

    def _toggle_click_through(self) -> None:
        (self.on_click_through or self.toggle_click_through)()

    def _toggle_visible(self) -> None:
        (self.on_visible or self.toggle_visible)()

    def _close_hit(self, x: int, y: int) -> bool:
        if self.cfg.click_through:
            return False
        width = int(self.cfg.width)
        x0 = width - PAD - CLOSE_SIZE
        y0 = PAD // 2
        return x0 <= x <= x0 + CLOSE_SIZE and y0 <= y <= y0 + CLOSE_SIZE

    def _on_left_press(self, event) -> None:
        if self.cfg.click_through:
            return
        if self._close_hit(event.x, event.y):
            self._request_quit()
            return
        self._drag_start(event)

    def _drag_start(self, event) -> None:
        if self.cfg.click_through:
            return
        self._drag = (event.x_root, event.y_root)

    def _drag_move(self, event) -> None:
        if self._drag is None:
            return
        dx = event.x_root - self._drag[0]
        dy = event.y_root - self._drag[1]
        self._drag = (event.x_root, event.y_root)
        self._x += dx
        self._y += dy
        self.root.geometry(f"{int(self.cfg.width)}x{self._height}+{self._x}+{self._y}")

    def _drag_end(self, _event) -> None:
        self._drag = None
        self.cfg.overlay_x = self._x
        self.cfg.overlay_y = self._y
        try:
            self.cfg.save()
        except OSError:
            pass

    # ------------------------------------------------------------ содержимое
    def set_view(self, view: HudView) -> None:
        try:
            self._queue.put_nowait(view)
        except queue.Full:
            pass

    def _drain(self) -> None:
        view = None
        while True:
            try:
                view = self._queue.get_nowait()
            except queue.Empty:
                break
        if view is not None:
            self._view = view
            self._draw(view)
        self.root.after(100, self._drain)

    def _draw(self, view: HudView) -> None:
        canvas = self.canvas
        cfg = self.cfg
        canvas.delete("all")
        width = int(cfg.width)

        route_font = self._font(1, bold=True)
        body_font = self._font(0)
        detail_font = self._font(-1)
        line_route = route_font.metrics("linespace")
        line_body = body_font.metrics("linespace")
        line_detail = detail_font.metrics("linespace")

        detail_lines = view.detail
        height = PAD + BAR_H + 6 + line_route + 4 + line_body + PAD
        if view.alert:
            height += line_detail + 2
        if detail_lines:
            height += 6 + line_detail * len(detail_lines)
        height = max(46, height)
        self._resize(height)

        canvas.configure(bg=cfg.color("panel"))
        canvas.create_rectangle(0, 0, width, height, fill=cfg.color("panel"), outline="")
        # полоска прогресса маршрута
        canvas.create_rectangle(0, 0, width, BAR_H, fill=cfg.color("bg"), outline="")
        if view.progress[1]:
            canvas.create_rectangle(
                0, 0, int(width * view.fraction), BAR_H, fill=cfg.color(view.accent), outline=""
            )
        canvas.create_line(0, height - 1, width, height - 1, fill=cfg.color("dim"))

        text_limit = width - PAD * 2
        if not cfg.click_through:
            text_limit -= CLOSE_SIZE + 6
            self._draw_close_button(width)

        y = PAD
        y = self._draw_row(view.route_row, PAD, y, route_font, width, text_limit=text_limit)
        y += 2
        y = self._draw_row(view.body_row, PAD, y, body_font, width, text_limit=text_limit)

        if view.alert:
            y += 1
            text = f"! {view.alert}"
            canvas.create_text(
                PAD, y, anchor="nw", text=text, fill=cfg.color("warn"), font=detail_font
            )
            y += line_detail

        if detail_lines:
            y += 4
            canvas.create_line(PAD, y, width - PAD, y, fill=cfg.color("dim"))
            y += 4
            for row in detail_lines:
                y = self._draw_row(
                    row, PAD + 2, y, detail_font, width, line_detail, text_limit=text_limit
                )

    def _draw_close_button(self, width: int) -> None:
        """Кнопка × — видна только когда сквозной режим выключен (F9)."""
        canvas = self.canvas
        cfg = self.cfg
        x0 = width - PAD - CLOSE_SIZE
        y0 = PAD // 2
        canvas.create_rectangle(
            x0,
            y0,
            x0 + CLOSE_SIZE,
            y0 + CLOSE_SIZE,
            fill=cfg.color("bg"),
            outline=cfg.color("dim"),
            tags=("close",),
        )
        canvas.create_text(
            x0 + CLOSE_SIZE // 2,
            y0 + CLOSE_SIZE // 2,
            text="×",
            fill=cfg.color("bad"),
            font=self._font(2, bold=True),
            tags=("close",),
        )

    def _draw_row(
        self,
        row,
        x: int,
        y: int,
        font,
        width: int,
        line_height: int | None = None,
        text_limit: int | None = None,
    ) -> int:
        canvas = self.canvas
        cfg = self.cfg
        limit = width - PAD * 2 if text_limit is None else text_limit
        cursor = x
        for segment in row.segments:
            if cursor > width - PAD:
                break
            text = segment.text
            if not text:
                continue
            seg_width = font.measure(text)
            if cursor + seg_width > limit:
                # обрезаем по символам
                while text and font.measure(text + "…") > limit - cursor:
                    text = text[:-1]
                if not text:
                    break
                text = text + "…"
                seg_width = font.measure(text)
            canvas.create_text(
                cursor,
                y,
                anchor="nw",
                text=text,
                fill=cfg.color(segment.style),
                font=font,
            )
            cursor += seg_width
            if text.endswith("…"):
                break
        metrics = font.metrics("linespace")
        return y + (line_height or metrics)

    # ------------------------------------------------------------- действия
    def toggle_expanded(self) -> None:
        self.cfg.expanded = not self.cfg.expanded

    def toggle_click_through(self) -> None:
        self.cfg.click_through = not self.cfg.click_through
        self._apply_click_through()

    def toggle_visible(self) -> None:
        self._visible = not self._visible
        if self._visible:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()

    def copy_to_clipboard(self, text: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception:
            pass

    def run(self) -> None:
        self.root.after(100, self._drain)
        self.root.mainloop()

    def destroy(self) -> None:
        if self._keeper is not None:
            self._keeper.stop()
        try:
            self.root.destroy()
        except Exception:
            pass

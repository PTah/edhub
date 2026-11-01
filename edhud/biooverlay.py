"""Второй оверлей слева: текущие био-находки, как PlotBioSystem у SrvSurvey.

Окно без рамки, поверх игры и сквозное для мыши вместе с основным дашбордом.
Появляется, только когда командир сам снял биосигналы в этой системе.
"""
from __future__ import annotations

from . import winapi
from .hudmodel import BioBoard, BioLine

PAD = 10
BAR_W = 8
BAR_H = 3


class BioPanel:
    def __init__(self, root, cfg) -> None:
        import tkinter as tk

        self.tk = tk
        self.cfg = cfg
        self._board: BioBoard | None = None
        self._parent_visible = True
        self._width = 280
        self._height = 80
        self._x = 16
        self._y = 96
        self._drag: tuple[int, int] | None = None
        self._fonts: dict[tuple[int, bool], object] = {}

        self.win = tk.Toplevel(root)
        self.win.title("EDHUD bio")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.withdraw()
        try:
            self.win.attributes("-alpha", max(0.25, min(1.0, float(cfg.opacity))))
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bd=0, bg=cfg.color("panel"))
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self._place_default()

    def hwnd(self) -> int:
        return winapi.hwnd_of(self.win)

    def wants_topmost(self) -> bool:
        return self._board is not None and self._parent_visible

    def set_alpha(self, alpha: float) -> None:
        try:
            self.win.attributes("-alpha", alpha)
        except Exception:
            pass

    def apply_click_through(self, click_through: bool) -> None:
        if not self.wants_topmost():
            return
        self.win.update_idletasks()
        winapi.apply_overlay_styles(
            self.hwnd(),
            click_through=click_through,
            topmost=bool(getattr(self.cfg, "keep_topmost", True)),
        )

    def set_parent_visible(self, visible: bool) -> None:
        self._parent_visible = visible
        self._sync()

    def set_board(self, board: BioBoard | None) -> None:
        self._board = board
        self._sync()

    def _sync(self) -> None:
        if self._board is None or not self._parent_visible:
            self.win.withdraw()
            return
        self._draw(self._board)
        self.win.deiconify()
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.apply_click_through(bool(self.cfg.click_through))

    def _place_default(self) -> None:
        self.win.update_idletasks()
        screen_h = self.win.winfo_screenheight()
        x = 16
        y = max(72, min(140, int(screen_h * 0.18)))
        if getattr(self.cfg, "bio_x", None) is not None:
            x = int(self.cfg.bio_x)
        if getattr(self.cfg, "bio_y", None) is not None:
            y = int(self.cfg.bio_y)
        self._x, self._y = x, y

    def _font(self, delta: int = 0, bold: bool = False):
        key = (delta, bold)
        if key not in self._fonts:
            from tkinter import font as tkfont

            family = self.cfg.font_family
            available = set(tkfont.families(self.win))
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

    def _text_width(self, segments, font) -> int:
        return sum(font.measure(segment.text) for segment in segments if segment.text)

    def _draw(self, board: BioBoard) -> None:
        canvas = self.canvas
        cfg = self.cfg
        canvas.delete("all")
        title_font = self._font(0, bold=True)
        font = self._font(-1)
        title_h = title_font.metrics("linespace")
        line_h = font.metrics("linespace")

        content = title_font.measure(board.title)
        for line in board.lines:
            extra = 18 if line.bars or line.bars_max else 0
            content = max(content, extra + self._text_width(line.segments + line.tail, font))
        for text, _style in board.footers:
            content = max(content, font.measure(text))
        screen_w = self.win.winfo_screenwidth()
        width = min(screen_w - 24, max(280, content + PAD * 2 + 8))

        height = PAD + title_h + 8
        for line in board.lines:
            if line.rule:
                height += 8
            height += line_h + 2
        if board.footers:
            height += 8 + line_h * len(board.footers)
        height += PAD

        screen_h = self.win.winfo_screenheight()
        x = max(0, min(self._x, screen_w - width))
        y = self._y
        if y + height > screen_h:
            y = max(0, screen_h - height)
        self._width, self._height = width, height
        self._x, self._y = x, y
        self.win.geometry(f"{width}x{height}+{x}+{y}")

        canvas.configure(bg=cfg.color("panel"), width=width, height=height)
        canvas.create_rectangle(0, 0, width, height, fill=cfg.color("panel"), outline="")
        canvas.create_rectangle(0, 0, 3, height, fill=cfg.color("fg"), outline="")

        y = PAD
        canvas.create_text(
            PAD, y, anchor="nw", text=board.title, fill=cfg.color("fg"), font=title_font
        )
        y += title_h + 4
        canvas.create_line(PAD, y, width - PAD, y, fill=cfg.color("dim"))
        y += 4
        for line in board.lines:
            if line.rule:
                canvas.create_line(PAD, y + 2, width - PAD, y + 2, fill=cfg.color("dim"))
                y += 8
            y = self._draw_line(line, y, font, width, line_h)
        if board.footers:
            y += 4
            canvas.create_line(PAD, y, width - PAD, y, fill=cfg.color("dim"))
            y += 4
            for text, style in board.footers:
                canvas.create_text(PAD, y, anchor="nw", text=text, fill=cfg.color(style), font=font)
                y += line_h

    def _draw_line(self, line: BioLine, y: int, font, width: int, line_h: int) -> int:
        x = PAD
        if line.bars or line.bars_max:
            self._draw_bars(x, y, line, line_h)
            x += BAR_W + 8
        limit = width - PAD
        tail_w = self._text_width(line.tail, font)
        main_w = self._text_width(line.segments, font)
        if line.tail and x + main_w + tail_w <= limit:
            tail_x = x + main_w
            main_limit = tail_x
        elif line.tail and tail_w < limit - x:
            tail_x = limit - tail_w
            main_limit = tail_x
        else:
            tail_x = None
            main_limit = limit
        self._draw_segments(line.segments, x, y, font, main_limit)
        if tail_x is not None:
            self._draw_segments(line.tail, tail_x, y, font, limit)
        return y + line_h + 2

    def _draw_bars(self, x: int, y: int, line: BioLine, line_h: int) -> None:
        canvas = self.canvas
        cfg = self.cfg
        filled = line.bars
        ghost = max(line.bars_max, line.bars)
        bottom = y + line_h - 2
        for level in range(1, 5):
            top = bottom - BAR_H
            if level <= filled:
                canvas.create_rectangle(x, top, x + BAR_W, bottom, fill=cfg.color("accent"), outline="")
            elif level <= ghost:
                canvas.create_rectangle(x, top, x + BAR_W, bottom, outline=cfg.color("dim"))
            bottom = top - 1

    def _draw_segments(self, segments, x: int, y: int, font, limit: int) -> None:
        canvas = self.canvas
        cfg = self.cfg
        cursor = x
        for segment in segments:
            if cursor >= limit or not segment.text:
                continue
            text = segment.text
            if cursor + font.measure(text) > limit:
                while text and font.measure(text + "…") > limit - cursor:
                    text = text[:-1]
                if not text:
                    break
                text += "…"
            canvas.create_text(
                cursor, y, anchor="nw", text=text, fill=cfg.color(segment.style), font=font
            )
            cursor += font.measure(text)

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
        self.win.geometry(f"{self._width}x{self._height}+{self._x}+{self._y}")

    def _drag_end(self, _event) -> None:
        self._drag = None
        self.cfg.bio_x = self._x
        self.cfg.bio_y = self._y
        try:
            self.cfg.save()
        except OSError:
            pass

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass

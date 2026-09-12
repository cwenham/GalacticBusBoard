"""
display.py
─────────────────────────────────────────────────────────────────────────────
Galactic Unicorn screen setup, drawing helpers, and button handling.

Exposes gu/graphics/W/H so other modules can measure text and draw directly
when they need to (e.g. api.py's pixel-fit destination abbreviation).
─────────────────────────────────────────────────────────────────────────────
"""

import time
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN

import config

# ── Display initialisation ────────────────────────────────────────────────
gu       = GalacticUnicorn()
graphics = PicoGraphics(display=DISPLAY_GALACTIC_UNICORN)
W        = GalacticUnicorn.WIDTH    # 53
H        = GalacticUnicorn.HEIGHT   # 11
LINE_HEIGHT = 10   # vertical pixel spacing between ticker lines (8px font + 2px gap)

graphics.set_font("bitmap8")
gu.set_brightness(config.BRIGHTNESS)

PEN_BG     = graphics.create_pen(0,   0,   0)
PEN_YELLOW = graphics.create_pen(255, 200,   0)
PEN_CYAN   = graphics.create_pen(0,   200, 200)
PEN_RED    = graphics.create_pen(200,   0,   0)
PEN_GREEN  = graphics.create_pen(0,   180,  60)
PEN_WHITE  = graphics.create_pen(160, 160, 160)


# ── Display helpers ───────────────────────────────────────────────────────

def clear():
    graphics.set_pen(PEN_BG)
    graphics.clear()


def handle_brightness():
    """Check brightness buttons and adjust if pressed. Call frequently."""
    if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_UP):
        gu.adjust_brightness(0.05)
    if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_DOWN):
        gu.adjust_brightness(-0.05)


# The four stop-select buttons on the left edge, plus the "Zzz" sleep
# button on the right edge, of the Galactic Unicorn.
ACTION_BUTTON_SWITCHES = {
    "A": GalacticUnicorn.SWITCH_A,
    "B": GalacticUnicorn.SWITCH_B,
    "C": GalacticUnicorn.SWITCH_C,
    "D": GalacticUnicorn.SWITCH_D,
    "SLEEP": GalacticUnicorn.SWITCH_SLEEP,
}

# Tracks whether each button was down on the previous check, so we can
# detect a fresh press (rising edge) rather than re-firing every frame for
# as long as the button is held.
_action_button_was_down = {k: False for k in ACTION_BUTTON_SWITCHES}


def check_action_button():
    """
    Poll the stop-select buttons and the sleep button. Returns the key
    ('A'..'D' or 'SLEEP') of a button that has just been freshly pressed,
    or None if none has. Simple rising-edge debounce: only fires once per
    press-and-release.
    """
    for key, switch in ACTION_BUTTON_SWITCHES.items():
        down = gu.is_pressed(switch)
        if down and not _action_button_was_down[key]:
            _action_button_was_down[key] = True
            return key
        if not down:
            _action_button_was_down[key] = False
    return None


def handle_buttons():
    """
    Call frequently from any wait/animation loop. Handles brightness
    adjustment and checks for a stop-select or sleep-button press. Returns
    the newly pressed key ('A'..'D', 'SLEEP') if one was just pressed,
    else None.
    """
    handle_brightness()
    return check_action_button()


def show_status(msg, pen=PEN_WHITE):
    """Show a short centred static message on the display."""
    clear()
    w = graphics.measure_text(msg, 1)
    graphics.set_pen(pen)
    graphics.text(msg, max(0, (W - w) // 2), 2, scale=1)
    gu.update(graphics)


def scroll_text(text, pen=PEN_YELLOW, duration_ms=None):
    """
    Scroll text left continuously.
    If duration_ms is given, stop after that many milliseconds.
    If duration_ms is None, scroll exactly once through the full text.
    Handles brightness buttons and stop-select buttons throughout;
    returns the pressed key ('A'..'D' or 'SLEEP') if one interrupts the scroll,
    otherwise None once the scroll completes normally.
    """
    text_width = graphics.measure_text(text, 1)
    offset     = 0
    deadline   = (time.ticks_add(time.ticks_ms(), duration_ms)
                  if duration_ms is not None else None)

    while True:
        clear()
        graphics.set_pen(pen)
        graphics.text(text, -offset, 2, scale=1)
        gu.update(graphics)
        time.sleep_ms(config.SCROLL_SPEED)

        pressed = handle_buttons()
        if pressed:
            return pressed

        offset += 1

        if deadline is not None:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return None
            # Seamless loop when running on a timer
            if offset > text_width + W:
                offset = 0
        else:
            # Single pass: stop once the text has fully scrolled off
            if offset > text_width + W:
                return None


def draw_row(left_text, right_text, y, pen):
    """Draw one row: left_text left-aligned at x=1, right_text right-
    justified to sit flush against the right edge of the display."""
    graphics.set_pen(pen)
    graphics.text(left_text, 1, y, scale=1)
    if right_text:
        rw = graphics.measure_text(right_text, 1)
        graphics.text(right_text, W - rw - 1, y, scale=1)


def show_static(left_text, right_text="", pen=PEN_WHITE, duration_ms=None):
    """
    Show a single static (non-scrolling) row, centred vertically, for
    duration_ms milliseconds — or indefinitely if duration_ms is None.
    Handles brightness and stop-select buttons throughout; returns the
    pressed key ('A'..'D' or 'SLEEP') if one interrupts the display, otherwise
    None once duration_ms elapses. Used for the "outside operating hours"
    display and for brief confirmation messages.

    The frame is redrawn on every tick (not just once up front) so that a
    brightness-button press takes effect on the display immediately,
    rather than only becoming visible once duration_ms finally elapses.
    """
    deadline = (time.ticks_add(time.ticks_ms(), duration_ms)
                if duration_ms is not None else None)
    while True:
        clear()
        draw_row(left_text, right_text, y=1, pen=pen)
        gu.update(graphics)

        pressed = handle_buttons()
        if pressed:
            return pressed
        time.sleep_ms(50)
        if deadline is not None and time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            return None


def scroll_lines(lines, pen=PEN_YELLOW, duration_ms=None, pause_ms=None):
    """
    Step through `lines` one at a time: hold each one static for `pause_ms`
    (defaults to config.PAUSE_SECONDS), then smoothly scroll up to reveal
    the next one. Cycles endlessly, including the wrap from the last line
    back to the first — that transition is animated exactly like every
    other transition, so there is never a visual jump.

    `lines` is a list of (left_text, right_text) tuples, each already
    guaranteed to fit within the display width (see api.build_display_lines).

    Handles brightness and stop-select buttons throughout; returns the
    pressed key ('A'..'D' or 'SLEEP') if one interrupts the display. Otherwise,
    if duration_ms is given, returns None once that much time has elapsed
    (after finishing whichever phase is in progress). If duration_ms is
    None, runs forever (until a stop button is pressed).
    """
    if not lines:
        lines = [("No data", "")]
    n = len(lines)

    if pause_ms is None:
        pause_ms = config.PAUSE_SECONDS * 1000

    deadline = (time.ticks_add(time.ticks_ms(), duration_ms)
                if duration_ms is not None else None)

    def expired():
        return deadline is not None and time.ticks_diff(deadline, time.ticks_ms()) <= 0

    idx = 0
    while True:
        left, right = lines[idx]

        # ── Static phase: hold this line for pause_ms ──────────────────
        clear()
        draw_row(left, right, y=1, pen=pen)
        gu.update(graphics)

        phase_deadline = time.ticks_add(time.ticks_ms(), pause_ms)
        while time.ticks_diff(phase_deadline, time.ticks_ms()) > 0:
            pressed = handle_buttons()
            if pressed:
                return pressed
            time.sleep_ms(20)
            if expired():
                return None

        # ── Transition phase: scroll up to the next line ───────────────
        nxt = (idx + 1) % n
        left2, right2 = lines[nxt]

        for step in range(1, LINE_HEIGHT + 1):
            clear()
            draw_row(left,  right,  y=1 - step,              pen=pen)
            draw_row(left2, right2, y=1 - step + LINE_HEIGHT, pen=pen)
            gu.update(graphics)
            time.sleep_ms(config.SCROLL_SPEED)
            pressed = handle_buttons()
            if pressed:
                return pressed
            if expired():
                return None

        idx = nxt
        if expired():
            return None

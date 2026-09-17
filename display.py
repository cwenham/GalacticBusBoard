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

PEN_BG     = graphics.create_pen(0,   0,   0)
PEN_YELLOW = graphics.create_pen(255, 200,   0)
PEN_CYAN   = graphics.create_pen(0,   200, 200)
PEN_RED    = graphics.create_pen(200,   0,   0)
PEN_GREEN  = graphics.create_pen(0,   180,  60)
PEN_WHITE  = graphics.create_pen(160, 160, 160)


# ── Brightness (manual + light-sensor auto-dimming) ───────────────────────
# _base_brightness is the level the user has dialled in with the physical
# brightness buttons. _is_dark tracks whether the room is currently dark.
# The brightness actually sent to the hardware is _base_brightness scaled
# by DARK_DIM_FACTOR while dark. Keeping these separate means dimming for
# darkness and the user's own brightness preference don't fight each other
# or drift when the room's light level changes.
_base_brightness    = config.BRIGHTNESS
_is_dark            = False
_last_light_check_ms = None


def _apply_brightness():
    factor = config.DARK_DIM_FACTOR if _is_dark else 1.0
    level  = max(0.0, min(1.0, _base_brightness * factor))
    gu.set_brightness(level)


_apply_brightness()   # set initial hardware brightness from config.BRIGHTNESS


def check_light_level():
    """
    Read the onboard light sensor (throttled to config.LIGHT_CHECK_INTERVAL)
    and enter/exit "dark mode" using hysteresis between DARK_THRESHOLD and
    LIGHT_RECOVER_THRESHOLD, so the display doesn't flicker between dim and
    bright when ambient light sits right at one threshold.
    """
    global _is_dark, _last_light_check_ms

    now = time.ticks_ms()
    if (_last_light_check_ms is not None and
            time.ticks_diff(now, _last_light_check_ms) < config.LIGHT_CHECK_INTERVAL * 1000):
        return
    _last_light_check_ms = now

    try:
        level = gu.light()
    except Exception as exc:
        print("Light sensor read error:", exc)
        return   # leave dark-mode state unchanged on a sensor glitch

    was_dark = _is_dark
    if _is_dark:
        if level > config.LIGHT_RECOVER_THRESHOLD:
            _is_dark = False
    else:
        if level < config.DARK_THRESHOLD:
            _is_dark = True

    if _is_dark != was_dark:
        print("Light level: {} -> {} dark mode".format(
            level, "entering" if _is_dark else "leaving"))
        _apply_brightness()


# ── Display helpers ───────────────────────────────────────────────────────

def clear():
    graphics.set_pen(PEN_BG)
    graphics.clear()


def handle_brightness():
    """
    Check brightness buttons and adjust the user's base brightness if
    pressed (auto-dimming for darkness is layered on top separately — see
    _apply_brightness). Also checks the light sensor. Call frequently.
    """
    global _base_brightness

    changed = False
    if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_UP):
        _base_brightness = min(1.0, _base_brightness + 0.05)
        changed = True
    if gu.is_pressed(GalacticUnicorn.SWITCH_BRIGHTNESS_DOWN):
        _base_brightness = max(0.0, _base_brightness - 0.05)
        changed = True
    if changed:
        _apply_brightness()

    check_light_level()


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


def draw_departure_row(line_no, dest, wait_str, y):
    """
    Draw one departure row with each part in its own colour for
    readability: the bus line number in white, the destination in yellow,
    and the arrival/wait time right-justified in cyan.
    """
    x = 1
    if line_no:
        graphics.set_pen(PEN_WHITE)
        graphics.text(line_no, x, y, scale=1)
        x += graphics.measure_text(line_no, 1)
        if dest:
            x += graphics.measure_text(" ", 1)

    if dest:
        graphics.set_pen(PEN_YELLOW)
        graphics.text(dest, x, y, scale=1)

    if wait_str:
        rw = graphics.measure_text(wait_str, 1)
        graphics.set_pen(PEN_CYAN)
        graphics.text(wait_str, W - rw - 1, y, scale=1)


def draw_cache_age_indicator(fraction):
    """
    Draw a cache-freshness gauge in the rightmost pixel column: a single
    green pixel at the top right immediately after a refresh, growing
    downward to fill the whole column as the cached data approaches
    poll_interval, shifting from green through yellow to red as it goes.

    fraction: 0.0 (just refreshed) to 1.0 (at or past poll_interval).
    Drawn as an overlay *after* the row text, in the column that's
    normally left blank by the 1px right margin the text layout already
    reserves — so it never displaces or narrows the text area.
    """
    fraction = max(0.0, min(1.0, fraction))

    # 1 pixel lit immediately after a refresh, growing to the full column
    # height (H) as fraction approaches 1.0.
    lit = 1 + int(fraction * (H - 1))
    lit = max(1, min(H, lit))

    if fraction <= 0.5:
        # green -> yellow across the first half
        t = fraction / 0.5
        r, g, b = int(255 * t), 200, 0
    else:
        # yellow -> red across the second half
        t = (fraction - 0.5) / 0.5
        r, g, b = 255, int(200 * (1 - t)), 0

    graphics.set_pen(graphics.create_pen(r, g, b))
    # A single filled rectangle is much cheaper than setting pixels one at
    # a time (the PicoGraphics docs note per-pixel drawing is slow), and
    # this needs to redraw every frame to animate smoothly.
    graphics.rectangle(W - 1, 0, 1, lit)


def show_static(left_text, right_text="", pen=PEN_WHITE, duration_ms=None, dim=False):
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

    dim=True forces the display down to config.SLEEP_DIM_BRIGHTNESS —
    "just about visible" — for as long as this call runs, regardless of
    the user's normal brightness setting. Used for the out-of-hours / Zzz
    (sleep) screen. The normal computed brightness (base level, further
    adjusted for ambient darkness) is restored on every way out of this
    function — a button press, the timeout, or nothing at all if dim was
    never requested.
    """
    deadline = (time.ticks_add(time.ticks_ms(), duration_ms)
                if duration_ms is not None else None)
    try:
        while True:
            clear()
            draw_row(left_text, right_text, y=1, pen=pen)
            if dim:
                gu.set_brightness(config.SLEEP_DIM_BRIGHTNESS)
            gu.update(graphics)

            pressed = handle_buttons()
            if pressed:
                return pressed
            time.sleep_ms(50)
            if deadline is not None and time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return None
    finally:
        if dim:
            _apply_brightness()   # restore the user's normal (base × dark-factor) level


def scroll_lines(lines, duration_ms=None, pause_ms=None,
                  cache_last_poll=None, cache_poll_interval=None):
    """
    Step through `lines` one at a time: hold each one static for `pause_ms`
    (defaults to config.PAUSE_SECONDS), then smoothly scroll up to reveal
    the next one. Cycles endlessly, including the wrap from the last line
    back to the first — that transition is animated exactly like every
    other transition, so there is never a visual jump.

    `lines` is a list of (line_no, dest, wait_str) tuples, each already
    guaranteed to fit within the display width (see api.build_display_lines).
    Each row is drawn with draw_departure_row, colouring line_no, dest,
    and wait_str differently for readability.

    If cache_last_poll (a time.time() timestamp) and cache_poll_interval
    (seconds) are both given, a cache-freshness gauge is drawn in the
    rightmost column after the row text — see draw_cache_age_indicator.
    Recomputed fresh every frame (in both phases below) so it animates
    smoothly and stays accurate to real elapsed time even while a line is
    held static, not just during the scrolling transitions.

    Handles brightness and stop-select buttons throughout; returns the
    pressed key ('A'..'D' or 'SLEEP') if one interrupts the display. Otherwise,
    if duration_ms is given, returns None once that much time has elapsed
    (after finishing whichever phase is in progress). If duration_ms is
    None, runs forever (until a stop button is pressed).
    """
    if not lines:
        lines = [("", "No data", "")]
    n = len(lines)

    if pause_ms is None:
        pause_ms = config.PAUSE_SECONDS * 1000

    show_age = cache_last_poll is not None and cache_poll_interval
    def age_fraction():
        if not show_age:
            return None
        return (time.time() - cache_last_poll) / cache_poll_interval

    deadline = (time.ticks_add(time.ticks_ms(), duration_ms)
                if duration_ms is not None else None)

    def expired():
        return deadline is not None and time.ticks_diff(deadline, time.ticks_ms()) <= 0

    idx = 0
    while True:
        line_no, dest, wait_str = lines[idx]

        # ── Static phase: hold this line for pause_ms ──────────────────
        # Redrawn every tick (not just once) so the cache-age indicator
        # keeps animating smoothly even while the line itself is static.
        phase_deadline = time.ticks_add(time.ticks_ms(), pause_ms)
        while True:
            clear()
            draw_departure_row(line_no, dest, wait_str, y=1)
            if show_age:
                draw_cache_age_indicator(age_fraction())
            gu.update(graphics)

            pressed = handle_buttons()
            if pressed:
                return pressed
            time.sleep_ms(20)
            if expired():
                return None
            if time.ticks_diff(phase_deadline, time.ticks_ms()) <= 0:
                break

        # ── Transition phase: scroll up to the next line ───────────────
        nxt = (idx + 1) % n
        line_no2, dest2, wait_str2 = lines[nxt]

        for step in range(1, LINE_HEIGHT + 1):
            clear()
            draw_departure_row(line_no,  dest,  wait_str,  y=1 - step)
            draw_departure_row(line_no2, dest2, wait_str2, y=1 - step + LINE_HEIGHT)
            if show_age:
                draw_cache_age_indicator(age_fraction())
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

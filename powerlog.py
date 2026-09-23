"""
powerlog.py
─────────────────────────────────────────────────────────────────────────────
Battery-life instrumentation: appends a periodic heartbeat line to a file on
the Pico's flash, so an unattended board that dies overnight still records
*when* it died.

This is experiment scaffolding, not a permanent feature — it exists to answer
"how much battery life did the WiFi power-down change actually buy?". Set
config.BATTERY_LOG_ENABLED = False to switch the whole thing off; every entry
point below is a cheap no-op when disabled.

Two details matter more than they look:

  • The log is opened in APPEND mode and never truncated. If it were cleared
    at boot, then powering a dead board back up would destroy the death
    timestamp — the single number the whole experiment is trying to collect.

  • Every line is flushed and the file closed immediately. A buffered write
    is lost when the battery cuts out, which is precisely the moment we care
    about. One open/write/close per heartbeat is wasteful in principle and
    completely irrelevant in practice at a 5-minute interval.
─────────────────────────────────────────────────────────────────────────────
"""

import time

import config
import clock


_uptime_s        = 0.0     # accumulated, not derived from the clock (see below)
_last_tick_ms    = None
_last_written_ms = None


def _update_uptime():
    """
    Accumulate uptime from ticks_ms deltas rather than from time.time().

    The wall clock is unreliable for this: it starts at the epoch before the
    first NTP sync, and jumps whenever a resync corrects drift, either of
    which would corrupt an uptime derived by subtraction. ticks_ms wraps
    (~12.4 days), but ticks_diff handles the wrap correctly as long as we
    sample more often than the wrap period — heartbeats every few minutes
    are comfortably inside it.
    """
    global _uptime_s, _last_tick_ms

    now = time.ticks_ms()
    if _last_tick_ms is not None:
        _uptime_s += time.ticks_diff(now, _last_tick_ms) / 1000.0
    _last_tick_ms = now


def _write(line):
    """Append one line and close immediately. Never raises."""
    try:
        with open(config.BATTERY_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception as exc:
        # A full or unwritable filesystem must not take the board down —
        # the display is the actual product, this is only instrumentation.
        print("powerlog write failed (continuing):", exc)


def _format(tag, fields):
    return "{} | up {:>7} | {:<9} | {}".format(
        clock.timestamp_str(), _uptime_str(), tag, fields)


def _uptime_str():
    if _uptime_s < 3600:
        return "{:.0f}m".format(_uptime_s / 60)
    return "{:.2f}h".format(_uptime_s / 3600)


def report_last_run():
    """
    Print the tail of the previous run's log to the serial console at boot.

    This is the payoff for the whole module: plug a dead board into USB and
    the last heartbeat before it died is right there in the console, instead
    of having to open the log file by hand and scroll to the end.
    """
    if not config.BATTERY_LOG_ENABLED:
        return

    try:
        with open(config.BATTERY_LOG_PATH, "r") as f:
            lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    except OSError:
        print("powerlog: no previous log (first run)")
        return

    if not lines:
        return

    print("powerlog: previous run ended at:")
    for ln in lines[-3:]:
        print("   ", ln)


def log_boot(time_is_synced):
    """
    Record a boot marker. Distinguishing a restart from a continuous run is
    what lets you tell "the battery died" from "it browned out and came
    back" when reading the log later.

    Note the clock is only meaningful here if NTP has already synced, hence
    the flag in the line — an unsynced boot timestamp is near the epoch and
    should not be mistaken for a real time.
    """
    if not config.BATTERY_LOG_ENABLED:
        return
    _update_uptime()
    _write("")   # blank line: visually separates runs in the file
    _write(_format("BOOT", "clock={}".format(
        "synced" if time_is_synced else "UNSYNCED — timestamp unreliable")))


def heartbeat(in_hours, is_dark, brightness, poll_count):
    """
    Append a heartbeat if config.BATTERY_LOG_INTERVAL has elapsed.

    Safe (and intended) to call every main-loop iteration — the throttle
    lives here so callers don't need their own timing state. The extra
    fields are logged because they drive power draw: a night spent dimmed
    and out-of-hours costs far less than a day at full brightness, so a
    run's duration means little without knowing the mix.
    """
    global _last_written_ms

    if not config.BATTERY_LOG_ENABLED:
        return

    _update_uptime()

    now = time.ticks_ms()
    if (_last_written_ms is not None and
            time.ticks_diff(now, _last_written_ms) < config.BATTERY_LOG_INTERVAL * 1000):
        return
    _last_written_ms = now

    _write(_format("HEARTBEAT", "hours={} dark={} bright={:.2f} polls={}".format(
        "open" if in_hours else "closed",
        "yes" if is_dark else "no",
        brightness,
        poll_count)))

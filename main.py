"""
main.py
─────────────────────────────────────────────────────────────────────────────
Pimoroni Galactic Unicorn (Raspberry Pi Pico W) – Live Bus Departure Board
─────────────────────────────────────────────────────────────────────────────
Polls the TransportAPI live bus stop endpoint and scrolls upcoming
departures across the 53×11 LED matrix. The poll interval is calculated
automatically from your operating hours and TransportAPI plan (see
AUTO_POLL_INTERVAL in config.py) so it stays within your daily quota.

Supports up to four bus stops, switchable with the Galactic Unicorn's A/B/C/D
buttons (see BUS_STOPS in config.py). Stop A defaults to Hove Station
(N-bound), ATCO 149000006680; stops B–D are configurable. The Zzz (sleep)
button forces the board open/closed regardless of the clock, until the
next real operating-hours boundary arrives — see main()'s hours_override
handling below.

Requirements
  • Pimoroni MicroPython firmware for Galactic Unicorn
      https://github.com/pimoroni/pimoroni-pico/releases
  • A free TransportAPI account (app_id + app_key)
      https://developer.transportapi.com

Plan quotas (as of writing — check developer.transportapi.com for current
figures if these seem out of date)
  • Free plan:            30 requests/day
  • Paid "Home user" plan: 300 requests/day (other paid tiers: adjust
    TRANSPORTAPI_PAID_DAILY_LIMIT in config.py to match your actual quota)

Files
  main.py     — this file: WiFi connection, stop switching, main event loop
  config.py   — all user-editable settings (WiFi, API keys, stops, timing)
  clock.py    — NTP sync, BST calculation, operating-hours window logic
  display.py  — Galactic Unicorn screen setup, drawing, button handling
  api.py      — TransportAPI HTTP client and display-line formatting
Copy all five files to the Pico W; MicroPython auto-runs main.py on boot.

Wiring / hardware
  No extra wiring needed. A/B/C/D switch bus stops; Zzz toggles sleep;
  the dedicated brightness buttons work independently throughout.
─────────────────────────────────────────────────────────────────────────────
"""

import time
import network

import config
import clock
import display
import api
import destinations


def connect_wifi():
    """Connect to WiFi, retrying until successful. Blocks until connected."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return

    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
    dots = 0
    while not wlan.isconnected():
        dots = (dots % 4) + 1
        display.show_status("WiFi" + "." * dots, display.PEN_CYAN)
        time.sleep(0.5)

    display.show_status("WiFi OK", display.PEN_GREEN)
    time.sleep(0.8)


def disconnect_wifi():
    """
    Power down the WiFi radio between polls. On a Pico W the radio draws
    meaningful current just sitting idle-connected — with poll_interval
    often several minutes, leaving it connected the whole time between
    fetches wastes a lot of battery for no benefit, since display refreshes
    use only the locally cached departures. Safe to call even if already
    disconnected; connect_wifi() fully re-activates and reconnects when
    next needed.
    """
    wlan = network.WLAN(network.STA_IF)
    try:
        if wlan.isconnected():
            wlan.disconnect()
        wlan.active(False)
    except Exception as exc:
        print("WiFi disconnect error (continuing):", exc)


def validate_bus_stops():
    """
    Warn at startup (via the serial log) about any configured stop that
    still holds the "YOUR_ATCO_CODE_x" placeholder, so a typo or unfinished
    config surfaces immediately rather than only when someone presses that
    stop's button in the field.
    """
    for key, cfg in config.BUS_STOPS.items():
        atco = cfg.get("atco", "")
        if not atco or atco.startswith("YOUR_ATCO_CODE"):
            print("Warning: stop '{}' ({}) has no ATCO code configured".format(
                key, cfg.get("name", "?")))


def switch_stop(new_key):
    """
    Handle a stop-select button press: validate it, show a brief
    confirmation, and return the new active key. Unconfigured stops
    (still holding the "YOUR_ATCO_CODE_x" placeholder) show a warning
    instead of silently trying to poll a bogus ATCO code.
    """
    cfg = config.BUS_STOPS.get(new_key)
    if cfg is None:
        return None  # shouldn't happen — unknown button key

    if not cfg["atco"] or cfg["atco"].startswith("YOUR_ATCO_CODE"):
        display.show_static("Stop " + new_key + " not set", pen=display.PEN_RED, duration_ms=1500)
        return None

    display.show_static(new_key + ": " + cfg["name"], pen=display.PEN_GREEN, duration_ms=1200)
    return new_key


def toggle_sleep(effective_open):
    """
    Handle a Zzz (sleep) button press: flip whichever state is currently
    showing, show a matching confirmation ("Sleeping" / "Waking up"), and
    return the new forced state. Shared by both branches of main()'s loop
    so the two call sites can't drift out of sync with each other.
    """
    new_state = not effective_open
    display.show_static("Waking up" if new_state else "Sleeping",
                         pen=display.PEN_CYAN, duration_ms=800)
    return new_state


def main():
    print("Galactic Bus Board starting")
    validate_bus_stops()
    connect_wifi()

    display.show_status("Clock...", display.PEN_CYAN)
    time_is_synced = clock.sync_time()   # if this fails, we fail open on hours (see clock.is_within_operating_hours)

    poll_interval        = api.compute_poll_interval()
    destination_overrides = destinations.load_overrides()

    active_stop_key = config.DEFAULT_STOP_KEY
    stop_cfg         = config.BUS_STOPS[active_stop_key]
    print("Active stop:", active_stop_key, stop_cfg["name"])

    # Each stop gets its own cached departures + last-poll timestamp, keyed
    # by stop letter. Switching stops (A/B/C/D) just changes which cache
    # entry is being shown — it does NOT force a fresh API call. A stop is
    # only re-polled once poll_interval has actually elapsed *for that
    # stop specifically*, same as if you'd left the board sitting on it the
    # whole time. This matters for the daily quota: repeatedly flicking
    # between stops (or briefly toggling sleep and un-toggling it) reuses
    # whatever's already cached instead of spending an extra API call.
    #
    # Note this does mean total daily usage scales with how many distinct
    # stops actually get viewed, since each is polled on its own schedule
    # once active — compute_poll_interval()'s quota math assumes a single
    # stop polled continuously all day. If you regularly view all four
    # stops for meaningful stretches, actual daily calls will run higher
    # than that calculation alone suggests.
    stop_cache = {key: {"departures": [], "last_poll": 0} for key in config.BUS_STOPS}

    last_ntp_sync = time.time()
    display_lines = [("", stop_cfg["name"] + " - loading...", "")]

    # Manual open/closed override, toggled by the Zzz (sleep) button.
    # None = no override, follow the schedule normally. True/False = force
    # open/closed regardless of the clock. Cleared automatically the next
    # time the *natural* schedule would flip anyway (see below), so the
    # override never lasts past the next real open/close boundary.
    hours_override = None
    last_natural    = clock.is_within_operating_hours(time_is_synced)

    while True:
        now = time.time()

        natural_open = clock.is_within_operating_hours(time_is_synced)

        # If the real schedule has flipped since we last checked, drop any
        # manual override — the board resumes automatic scheduling and
        # simply shows whatever the schedule now says.
        if hours_override is not None and natural_open != last_natural:
            hours_override = None
        last_natural = natural_open

        effective_open = hours_override if hours_override is not None else natural_open

        cache_entry = stop_cache[active_stop_key]

        # Work out up front whether WiFi is needed at all this cycle —
        # either the clock needs a resync, or (while open) the active
        # stop's own cache has gone stale. At most one connect/disconnect
        # cycle happens per loop iteration even if both are due, since
        # both network operations share the same "WiFi up" window below.
        ntp_due  = time.time() - last_ntp_sync >= config.NTP_RESYNC_INTERVAL
        poll_due = effective_open and (
            cache_entry["last_poll"] == 0 or now - cache_entry["last_poll"] >= poll_interval)

        if ntp_due or poll_due:
            connect_wifi()   # no-op if already connected

            if ntp_due:
                if clock.sync_time():
                    time_is_synced = True
                    last_ntp_sync  = time.time()

            if poll_due:
                # Note: this checks last_poll == 0 (the initial sentinel),
                # NOT "not cache_entry['departures']". A successful poll
                # can quite legitimately return an empty list (a real gap
                # between scheduled buses), and treating that as "cache
                # not populated" would force a fresh fetch every loop
                # iteration until a non-empty result eventually came back
                # — bypassing poll_interval and burning the daily quota.
                result = api.fetch_departures(stop_cfg["atco"])
                if result is not None:
                    cache_entry["departures"] = result
                    print("Departures ({}):".format(active_stop_key), result)
                cache_entry["last_poll"] = time.time()

            disconnect_wifi()

        # ── Outside effective hours: don't poll, just show the message ──
        # (Caches are left untouched here rather than cleared: if hours
        # reopen shortly after — e.g. a brief manual sleep toggle — the
        # still-fresh cached data is shown immediately rather than forcing
        # a needless extra API call. After a long closure, the elapsed
        # time will naturally exceed poll_interval anyway, so poll_due
        # above will trigger a fresh poll on reopening as usual.)
        if not effective_open:
            pressed = display.show_static(config.OUT_OF_HOURS_MESSAGE,
                                           duration_ms=config.OUT_OF_HOURS_CHECK_INTERVAL * 1000,
                                           dim=True)
            if pressed == "SLEEP":
                hours_override = toggle_sleep(effective_open)
            elif pressed and pressed != active_stop_key:
                new_key = switch_stop(pressed)
                if new_key:
                    active_stop_key = new_key
                    stop_cfg        = config.BUS_STOPS[active_stop_key]
            continue

        # Rebuild the display lines (cheap – no network call) so the
        # "Xm" values stay accurate between API polls
        display_lines = api.build_display_lines(cache_entry["departures"], destination_overrides)

        # Scroll for COUNTDOWN_REFRESH seconds, then loop round to
        # recompute the countdown (and poll/re-sync/re-check hours again).
        # A stop button switches immediately; the sleep button forces
        # closed immediately — neither waits for the countdown to finish.
        # WiFi is off throughout this whole wait (see above) since only
        # the locally cached departures are needed to keep the display
        # updated during it.
        pressed = display.scroll_lines(display_lines, duration_ms=config.COUNTDOWN_REFRESH * 1000,
                                        cache_last_poll=cache_entry["last_poll"],
                                        cache_poll_interval=poll_interval)
        if pressed == "SLEEP":
            hours_override = toggle_sleep(effective_open)
        elif pressed and pressed != active_stop_key:
            new_key = switch_stop(pressed)
            if new_key:
                active_stop_key = new_key
                stop_cfg        = config.BUS_STOPS[active_stop_key]
                # No cache reset here — the newly active stop's own cached
                # data (if any, and if still fresh) is shown as-is. The
                # poll_due check above will fetch automatically next cycle
                # if it's empty or past its own poll_interval.


main()

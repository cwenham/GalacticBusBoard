# GalacticBusBoard

Live bus departure board: a Pimoroni Galactic Unicorn (53×11 RGB LED matrix with
onboard Raspberry Pi Pico W) running MicroPython, polling TransportAPI for
real-time departures and scrolling them on the display.

The source is heavily commented and the rationale for most individual decisions
lives next to the code it explains. This file covers what the source can't tell
you: the platform's sharp edges, project-wide conventions, and alternatives that
were tried and rejected.

## Platform

- **Firmware must be Pimoroni's MicroPython build** for this board (from
  `pimoroni-pico` releases), not stock Raspberry Pi MicroPython — the `galactic`
  and `picographics` modules don't exist in the stock build.
- **MicroPython, not CPython.** Assumptions that don't hold: no `csv` module
  (hence the hand-rolled parser in `destinations.py`), no
  `usocket.setdefaulttimeout()`, the SSL module is `ssl` not `ussl`, and
  `urequests` is present but unusable here (see Rejected below).
- **No timezone database.** NTP gives UTC, TransportAPI gives UK local time.
  `clock.is_bst()` computes the last-Sunday-of-March / last-Sunday-of-October
  transitions by hand.
- **No persistence across reboots.** `stop_cache`, `last_poll`, `hours_override`
  and friends are RAM-only and reset on power loss.

## Constraints that shape the design

- **53×11 pixels.** Roughly 8–9 characters per line at the bitmap8 font. This is
  the single biggest constraint on `display.py` and is why destination
  abbreviation, the `destinations.csv` override table, and per-role colouring
  (line number white, destination yellow, wait time cyan) all exist.
- **TransportAPI's daily request quota is hard, not advisory.** The calculated
  poll interval and per-stop caching are both built around it. Any change that
  could increase API call frequency needs to be checked against the quota maths
  in `api.compute_poll_interval()`.
- **Battery-powered, unattended deployment is a live constraint**, not
  hypothetical. Power cost is a real consideration for any new work.

## Conventions

- **`import config` + `config.NAME`**, never `from config import (...)`. Settings
  get added often, and the tuple-import form meant editing a growing import list
  across several files every time.
- **Don't create a module named `network.py`** — it would shadow MicroPython's
  built-in `network`. This is why `connect_wifi()` / `disconnect_wifi()` live in
  `main.py` rather than in a module of their own.
- **Avoid per-pixel drawing.** Use `graphics.rectangle()` and friends;
  PicoGraphics' own docs note `pixel()` in a loop is slow.
- **Fail open, not closed.** If the clock has never synced,
  `is_within_operating_hours()` returns `True` — a board stuck showing buses is a
  smaller failure than one stuck showing "No busses", given what it's for.

## Rejected alternatives

Don't re-propose these without new information:

- **UK Bus Open Data Service (BODS)** — free and official, but only exposes
  SIRI-VM (vehicle positions, route start/end), not SIRI-SM (stop-level
  departures). A given stop is essentially never a route's first or last stop, so
  a vehicle-position feed can't answer "what's coming to this stop."
  TransportAPI's `stop_timetables` endpoint does.
- **`urequests` for API calls** — two real bugs: `get()` doesn't accept a
  `timeout=` kwarg in MicroPython, and `resp.text`/`.content` silently return an
  empty string for chunked transfer encoding, which TransportAPI's server uses.
  `api.https_get()` speaks raw-socket HTTP/1.0 specifically because HTTP/1.0
  predates chunked encoding.
- **`usocket.setdefaulttimeout()`** — doesn't exist in MicroPython.
- **Pre-dividing the daily quota across all four stops** — would slow the primary
  stop's refresh to guard against a usage pattern (frequent stop switching) that
  isn't the actual one (occasional peeks). Revisit only if usage changes.
- **Reducing `gu.update()` call frequency to save power** — the matrix hardware
  re-refreshes the last-pushed frame at its own fixed rate regardless, so this
  saves only CPU, which isn't the dominant draw.
- **`machine.deepsleep()`** — on RP2040 MicroPython it's lightsleep-then-reset,
  which loses all in-RAM state. Using it properly would mean restructuring the
  program around saving/restoring state to flash every sleep cycle.
- **`machine.lightsleep()`** — *deferred, not ruled out.* It gives negligible
  benefit while WiFi stays connected, and has a history of firmware-version
  -dependent breakage on the Pico W (USB dropping, GPIO-wake-from-lightsleep
  broken in some releases). The WiFi power-down change was done first as the
  lower-risk fix; whether to take on the compatibility risk depends on how much
  that change actually bought.

## Bug shapes to watch for

The costly bugs here have all been subtle logic errors in the quota/timing code
rather than crashes. The canonical one: using `not cache_entry["departures"]` as
a "never fetched yet" signal, when an empty departures list is a *legitimate*
API result (a real gap in the timetable). That made the board refetch every
60-second loop tick whenever a poll returned no buses, silently bypassing
`poll_interval`. It was only caught from a TransportAPI usage dashboard showing
bursty rather than steady call patterns. If something "works fine" but the call
count doesn't match the maths, look for this shape.

There is no automated test suite. The hardware-independent logic (BST
calculation, poll-interval maths, operating-hours window arithmetic, pixel-fit
trimming, CSV parsing) was verified by one-off manual simulation during
development.

"""
config.py
─────────────────────────────────────────────────────────────────────────────
Configuration for the Galactic Bus Board (see main.py).

Edit the values below, then copy this file to the Pico W alongside the
other modules (e.g. via Thonny) — see main.py's docstring for the full
file list. Keeping credentials here means you can share or
version-control the rest of the board's code without exposing secrets.
─────────────────────────────────────────────────────────────────────────────
"""

# ── WiFi ──────────────────────────────────────────────────────────────────
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

# ── TransportAPI credentials ────────────────────────────────────────────
# Get these from https://developer.transportapi.com
TRANSPORTAPI_APP_ID  = "YOUR_APP_ID"
TRANSPORTAPI_APP_KEY = "YOUR_APP_KEY"

# ── Bus stops ────────────────────────────────────────────────────────────
# The Galactic Unicorn has four buttons (A, B, C, D) on its left edge.
# Pressing one switches the board to show that stop's departures. Look up
# ATCO codes at https://naptan.api.dft.gov.uk or via www.buses.co.uk.
BUS_STOPS = {
    "A": {"name": "Hove Station N", "atco": "149000006680"},
    "B": {"name": "Stop B",          "atco": "YOUR_ATCO_CODE_B"},
    "C": {"name": "Stop C",          "atco": "YOUR_ATCO_CODE_C"},
    "D": {"name": "Stop D",          "atco": "YOUR_ATCO_CODE_D"},
}

# Which stop is shown when the board first boots up.
DEFAULT_STOP_KEY = "A"

# ── Behaviour ────────────────────────────────────────────────────────────
# The polling interval is calculated automatically (see AUTO_POLL_INTERVAL
# below) from your operating hours window and TransportAPI plan, so that
# polling continuously throughout the day stays within your daily quota.
MAX_DEPARTURES  = 6      # maximum departures to show per scroll cycle
SCROLL_SPEED    = 30     # milliseconds per pixel of scroll movement
BRIGHTNESS      = 0.5    # initial display brightness, 0.0–1.0

# ── Polling interval ─────────────────────────────────────────────────────
# If True, the poll interval is calculated automatically from your
# operating hours (see below) and TransportAPI plan's daily request quota:
#   poll_interval = (operating window in minutes) / (daily request quota)
# e.g. a 2-hour operating window on the free plan (30 requests/day) gives
# a 4-minute poll interval. If False, POLL_INTERVAL is used as-is instead.
AUTO_POLL_INTERVAL = True
POLL_INTERVAL       = 1800   # seconds — only used if AUTO_POLL_INTERVAL is False

# Which TransportAPI plan you're on: "free" or "paid". Determines which of
# the two daily-limit values below is used in the calculation above.
TRANSPORTAPI_PLAN = "free"

# TransportAPI's Free plan: 30 requests/day (https://developer.transportapi.com)
TRANSPORTAPI_FREE_DAILY_LIMIT = 30

# TransportAPI's paid "Home user" plan: 300 requests/day. If you're on a
# different paid tier, change this to match your plan's actual daily quota.
TRANSPORTAPI_PAID_DAILY_LIMIT = 300

# Safety floor: never poll more often than this, regardless of what the
# quota math above works out to (protects against a very short operating
# window or high quota producing an unreasonably aggressive poll rate).
MIN_POLL_INTERVAL_SECONDS = 30

# How often to recompute "minutes until arrival" without re-polling the API.
# Keeping this short makes the countdown feel live between API polls.
COUNTDOWN_REFRESH = 60        # seconds

# How long to hold each bus's departure line static before scrolling to
# the next one.
PAUSE_SECONDS = 4

# Remove a bus from the display once it's been "Due" (i.e. past its
# scheduled departure time) for longer than this many minutes.
DUE_CUTOFF_MINUTES = 2

# ── Operating hours ────────────────────────────────────────────────────
# The board only polls the API and shows departures between these times
# (UK local time, 24h "HH:MM"). Outside this window it shows
# OUT_OF_HOURS_MESSAGE and doesn't call the API — handy for saving your
# TransportAPI daily quota overnight. Set END earlier than START to span
# midnight (e.g. "06:00" to "00:30" covers 6am through to 12:30am).
OPERATING_HOURS_START = "06:00"
OPERATING_HOURS_END   = "00:30"
OUT_OF_HOURS_MESSAGE  = "No busses"

# How often to re-check the clock / redraw while outside operating hours.
OUT_OF_HOURS_CHECK_INTERVAL = 300   # seconds (5 minutes)

# How often to re-sync the Pico's clock against an NTP server, to correct
# for RTC drift on long-running deployments.
NTP_RESYNC_INTERVAL = 21600   # seconds (6 hours)

# ── Auto-dimming (onboard light sensor) ───────────────────────────────────
# The Galactic Unicorn has a built-in phototransistor; gu.light() returns a
# raw reading from 0 (dark) to 4095 (bright). When it drops below
# DARK_THRESHOLD, the display dims to BRIGHTNESS * DARK_DIM_FACTOR. It only
# brightens back up once the reading rises above LIGHT_RECOVER_THRESHOLD —
# that gap (rather than a single threshold) stops the display flickering
# between dim/bright if the ambient light hovers right at the boundary.
#
# These defaults are a starting guess, not a measured calibration — the
# sensor's real-world readings depend heavily on where the board is mounted
# (behind a diffuser, near a window, etc). Watch the serial log for lines
# like "Light level: 812 -> entering dark mode" to see actual readings in
# your setup and adjust the thresholds accordingly.
DARK_THRESHOLD          = 50    # below this: dim the display
LIGHT_RECOVER_THRESHOLD = 150   # above this: return to full brightness
DARK_DIM_FACTOR         = 0.5   # brightness multiplier while dark (0.5 = half)
LIGHT_CHECK_INTERVAL    = 5     # seconds between light-sensor reads

# How dim the out-of-hours / Zzz (sleep) screen should be — deliberately
# much lower than DARK_DIM_FACTOR, since this is a "barely visible, don't
# light up the room" state rather than just a slightly-dimmer display.
SLEEP_DIM_BRIGHTNESS = 0.03

# ── Destination short-name overrides ──────────────────────────────────────
# Path (on the Pico's filesystem) to a CSV file of curated short names for
# destinations that abbreviate awkwardly on their own (e.g. "Shooting
# Field" trimming down to just "Shoot"). Columns: ID (integer), Stop Name,
# Short Name — a header row is optional. See destinations.py for the
# loader and destinations.csv for an example. If the file is missing, the
# board falls back to purely algorithmic pixel-fit trimming as before.
DESTINATION_OVERRIDES_CSV = "destinations.csv"

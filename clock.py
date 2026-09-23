"""
clock.py
─────────────────────────────────────────────────────────────────────────────
NTP time sync and UK-local-time / operating-hours logic for the bus board.

The Pico W's RTC is not set on boot, and TransportAPI departure times are
UK local time (which shifts by an hour during British Summer Time), so we
sync to NTP (UTC) and then apply the BST offset ourselves.
─────────────────────────────────────────────────────────────────────────────
"""

import time
import ntptime

import config


def sync_time():
    """Sync the Pico's RTC to NTP (UTC). Safe to call repeatedly."""
    try:
        ntptime.settime()
        print("NTP sync OK:", time.localtime())
        return True
    except Exception as exc:
        print("NTP sync failed:", exc)
        return False


def is_bst(t):
    """
    Return True if the given UTC time tuple falls within UK British Summer
    Time. BST runs from 01:00 UTC on the last Sunday of March to 01:00 UTC
    on the last Sunday of October.
    t is a time.localtime()-style tuple: (year, month, mday, hour, min, ...).
    """
    year, month, mday, hour = t[0], t[1], t[2], t[3]

    if month < 3 or month > 10:
        return False
    if 3 < month < 10:
        return True

    # In March or October: find the last Sunday of that month.
    # weekday(): time.localtime()[6] is 0=Monday..6=Sunday in MicroPython.
    def last_sunday(y, m):
        # Start from the last day of the month and walk back to Sunday.
        days_in_month = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        d = days_in_month[m - 1]
        while True:
            wd = time.mktime((y, m, d, 1, 0, 0, 0, 0))
            wd = time.localtime(wd)[6]
            if wd == 6:  # Sunday
                return d
            d -= 1

    boundary_day = last_sunday(year, month)

    if month == 3:
        if mday > boundary_day:
            return True
        if mday < boundary_day:
            return False
        return hour >= 1   # BST starts 01:00 UTC on the boundary Sunday
    else:  # October
        if mday < boundary_day:
            return True
        if mday > boundary_day:
            return False
        return hour < 1    # BST ends 01:00 UTC on the boundary Sunday


def uk_local_minutes():
    """
    Return the current UK local time as minutes-since-midnight (0–1439),
    adjusting the NTP-synced UTC clock for BST when applicable.
    """
    t = time.localtime()
    hour, minute = t[3], t[4]
    if is_bst(t):
        hour += 1
        if hour >= 24:
            hour -= 24
    return hour * 60 + minute


def uk_local_tuple():
    """
    Return the current time as a UK-local time tuple, applying the BST
    offset by adding an hour to the epoch value rather than to the hour
    field — so a shift across midnight rolls the date correctly too.
    (uk_local_minutes() above applies the same offset, but only ever needs
    minutes-since-midnight, where the date rollover doesn't matter.)
    """
    t = time.localtime()
    if is_bst(t):
        t = time.localtime(time.mktime(t) + 3600)
    return t


def timestamp_str():
    """
    UK local time as "YYYY-MM-DD HH:MM:SS", for log lines.

    Note this is only meaningful once NTP has synced — before that the RTC
    reads from its power-on epoch, so callers that might run pre-sync
    should record whether the clock was synced alongside the timestamp.
    """
    t = uk_local_tuple()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5])


def parse_hhmm(s):
    """Parse an "HH:MM" string into minutes-since-midnight."""
    h, m = s.split(":")
    return int(h) * 60 + int(m)


_OPERATING_START_MIN = parse_hhmm(config.OPERATING_HOURS_START)
_OPERATING_END_MIN   = parse_hhmm(config.OPERATING_HOURS_END)


def is_within_operating_hours(time_is_synced):
    """
    Return True if the board should be polling/showing departures right
    now. If the clock has never been successfully synced (e.g. no network
    at boot), fail OPEN rather than closed — better to show slightly
    unfiltered/live data than to brick the display because of a clock
    problem, since a wrong "no buses" state is worse than a wrong "show
    buses" state on a device whose whole purpose is to display them.
    """
    if not time_is_synced:
        return True

    now = uk_local_minutes()
    start, end = _OPERATING_START_MIN, _OPERATING_END_MIN

    if start <= end:
        # Normal same-day window, e.g. 06:00–23:00
        return start <= now < end
    else:
        # Window spans midnight, e.g. 06:00–00:30
        return now >= start or now < end


def operating_window_minutes():
    """
    Length of the configured operating-hours window in minutes, handling
    windows that span midnight. If start == end, treat it as a full 24h
    window rather than a zero-length one.
    """
    duration = (_OPERATING_END_MIN - _OPERATING_START_MIN) % 1440
    return duration if duration != 0 else 1440

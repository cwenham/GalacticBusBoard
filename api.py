"""
api.py
─────────────────────────────────────────────────────────────────────────────
TransportAPI client: builds requests, performs the (chunked-encoding-safe)
raw HTTPS fetch, parses the JSON response into departure records, and
formats those records into pixel-fit display lines.
─────────────────────────────────────────────────────────────────────────────
"""

import gc
import json
import math
import usocket
import ssl

import config
import clock
import display


def build_api_url(atco):
    """Build the TransportAPI live-departures URL for a given ATCO code."""
    return (
        "https://transportapi.com/v3/uk/bus/stop_timetables/{atco}.json"
        "?app_id={app_id}&app_key={app_key}&group=false&live=true"
    ).format(atco=atco, app_id=config.TRANSPORTAPI_APP_ID, app_key=config.TRANSPORTAPI_APP_KEY)


def https_get(url, max_redirects=3):
    """
    Perform an HTTPS GET using raw sockets with HTTP/1.0 (no chunked
    encoding). Follows up to max_redirects 301/302 redirects.
    Returns the response body as a string, or raises on error.
    """
    for _ in range(max_redirects + 1):
        _, _, host, path = url.split("/", 3)
        path = "/" + path

        ai   = usocket.getaddrinfo(host, 443, 0, usocket.SOCK_STREAM)
        sock = usocket.socket(usocket.AF_INET, usocket.SOCK_STREAM)
        sock.connect(ai[0][-1])
        sock = ssl.wrap_socket(sock, server_hostname=host)

        request = (
            "GET {path} HTTP/1.0\r\n"
            "Host: {host}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).format(path=path, host=host)
        sock.write(request.encode())

        buf = b""
        while True:
            chunk = sock.read(1024)
            if not chunk:
                break
            buf += chunk
        sock.close()

        # Split headers and body
        sep     = buf.find(b"\r\n\r\n")
        headers = buf[:sep].decode("utf-8") if sep != -1 else ""
        body    = buf[sep + 4:].decode("utf-8") if sep != -1 else buf.decode("utf-8")
        del buf

        # Check status code (first header line: "HTTP/1.x 3xx ...")
        status_line = headers.split("\r\n")[0]
        status = int(status_line.split()[1])
        print("HTTP", status, url[:60])

        if status in (301, 302, 303, 307, 308):
            # Extract Location header
            location = ""
            for line in headers.split("\r\n")[1:]:
                if line.lower().startswith("location:"):
                    location = line.split(":", 1)[1].strip()
                    break
            if not location:
                raise Exception("Redirect with no Location header")
            print("Redirect ->", location[:60])
            url = location
            continue

        if status != 200:
            raise Exception("HTTP " + str(status))

        return body

    raise Exception("Too many redirects")


def fetch_departures(atco):
    """
    Call the TransportAPI live stop endpoint for the given ATCO code and
    return a list of departure dicts:
      [{"line": "1", "dest": "City Centre", "time": "14:32"}, …]

    The JSON response looks like:
    {
      "departures": {
        "5B": [
          {
            "line_name":             "5B",
            "direction":             "Old Shoreham Road",
            "aimed_departure_time":  "14:28",
            "expected_departure_time": "14:30",
            "best_departure_estimate": "14:30"
          },
          ...
        ],
        ...
      }
    }
    Departures are grouped by line; we flatten and sort by best time.
    """
    display.show_status("Loading", display.PEN_CYAN)
    gc.collect()

    try:
        raw = https_get(build_api_url(atco))
    except MemoryError:
        print("MemoryError during fetch")
        display.show_status("Mem Err", display.PEN_RED)
        gc.collect()
        return None
    except Exception as exc:
        msg = str(exc)
        print("Fetch error:", msg)
        display.scroll_text("API error: " + msg, pen=display.PEN_RED)
        return None

    gc.collect()

    try:
        data = json.loads(raw)
    except Exception as exc:
        print("JSON parse error:", exc)
        display.scroll_text("Bad JSON: " + str(exc)[:20], pen=display.PEN_RED)
        del raw
        gc.collect()
        return None

    del raw
    gc.collect()

    departures_by_line = data.get("departures", {})
    if not departures_by_line:
        print("No departures in response")
        return []

    flat = []
    for line_key, services in departures_by_line.items():
        for svc in services:
            # Use the best available time estimate
            dep_time = (svc.get("expected_departure_time")
                        or svc.get("best_departure_estimate")
                        or svc.get("aimed_departure_time")
                        or "??:??")

            dest = (svc.get("direction") or line_key).strip()
            # Drop trailing qualifiers like "Brighton, via Seafront" or
            # "Churchill Square via North Street" - keep the primary name;
            # exact-width abbreviation happens later in build_display_lines.
            for cut in (",", " via "):
                idx = dest.find(cut)
                if idx > 0:
                    dest = dest[:idx]
            dest = dest.strip()

            line = (svc.get("line_name") or line_key).strip()

            flat.append({"line": line, "dest": dest, "time": dep_time})

    # Sort by departure time (HH:MM strings sort correctly lexicographically)
    flat.sort(key=lambda d: d["time"])
    return flat[:config.MAX_DEPARTURES]


def minutes_until(dep_time_str):
    """
    Convert an "HH:MM" departure time string into minutes from now, using
    the current UK local time. Handles midnight rollover. Returns None if
    dep_time_str isn't parseable.
    """
    try:
        h, m = dep_time_str.split(":")
        dep_minutes = int(h) * 60 + int(m)
    except Exception:
        return None

    now_minutes = clock.uk_local_minutes()
    diff = dep_minutes - now_minutes

    # If very negative, the departure is actually just after midnight
    # tomorrow (e.g. now=23:58, dep=00:05 -> diff would be -1433).
    if diff < -720:
        diff += 1440

    return diff


def build_display_lines(departures):
    """
    Format departures into a list of (left_text, right_text) tuples, one
    per bus. right_text (the wait time) is drawn right-justified against
    the screen edge; left_text (line number + abbreviated destination) is
    drawn left-aligned. The destination is trimmed to whatever fits in the
    remaining space, since it's the least critical piece of information
    once you know the line number and direction.
    """
    if not departures:
        return [("No departures found", ""), ("Next check soon", "")]

    # Drop buses that departed more than DUE_CUTOFF_MINUTES ago — they're
    # almost certainly gone and just clutter the board. minutes_until()
    # returns a small negative number once a bus is overdue; a large
    # negative number (from the day-rollover case) is left alone since
    # that actually represents a bus departing soon after midnight.
    active = []
    for d in departures:
        mins = minutes_until(d["time"])
        if mins is not None and -720 < mins < -config.DUE_CUTOFF_MINUTES:
            continue   # overdue for too long — remove
        active.append(d)

    if not active:
        return [("No departures found", ""), ("Next check soon", "")]
    departures = active

    GAP = 2   # minimum pixel gap between the left and right text blocks
    lines = []

    for d in departures:
        mins = minutes_until(d["time"])
        if mins is None:
            wait_str = d["time"]
        elif mins <= 0:
            wait_str = "Due"
        else:
            wait_str = "{}m".format(mins)

        line_no = d["line"]
        sep     = " "

        # Reserve pixel width for the right-justified wait time
        right_width    = display.graphics.measure_text(wait_str, 1)
        right_x        = display.W - right_width - 1     # 1px right margin
        max_left_width = right_x - 1 - GAP                # left text starts at x=1

        dest = d["dest"]
        left_text = (line_no + sep + dest) if dest else line_no
        while dest and display.graphics.measure_text(left_text, 1) > max_left_width:
            dest = dest[:-1]
            left_text = (line_no + sep + dest) if dest else line_no

        # Safety net: on an unusually long line name (e.g. "Coaster") even
        # line_no alone might not fit. Trim it as a last resort so the
        # left text never collides with the right-justified wait time.
        while display.graphics.measure_text(left_text, 1) > max_left_width and len(line_no) > 1:
            line_no   = line_no[:-1]
            left_text = line_no

        lines.append((left_text, wait_str))

    return lines


def compute_poll_interval():
    """
    Work out how often to poll the API in seconds.

    If config.AUTO_POLL_INTERVAL is enabled, this sizes the interval so
    that polling continuously across the whole operating-hours window each
    day stays within the configured TransportAPI plan's daily request quota:

        poll_interval = (operating window in minutes) / (daily quota)

    e.g. a 2-hour operating window on the free plan (30 requests/day)
    gives exactly 4 minutes between polls. The result is rounded UP (never
    down) so the quota is never exceeded, and is floored at
    config.MIN_POLL_INTERVAL_SECONDS as a sanity limit.

    If config.AUTO_POLL_INTERVAL is False, config.POLL_INTERVAL is used as-is.
    """
    if not config.AUTO_POLL_INTERVAL:
        return config.POLL_INTERVAL

    daily_limit = (config.TRANSPORTAPI_FREE_DAILY_LIMIT if config.TRANSPORTAPI_PLAN == "free"
                   else config.TRANSPORTAPI_PAID_DAILY_LIMIT)
    if daily_limit <= 0:
        print("Invalid daily limit for plan '{}', falling back to POLL_INTERVAL".format(config.TRANSPORTAPI_PLAN))
        return config.POLL_INTERVAL

    window_min       = clock.operating_window_minutes()
    interval_min     = window_min / daily_limit
    interval_seconds = int(math.ceil(interval_min * 60))
    interval_seconds = max(config.MIN_POLL_INTERVAL_SECONDS, interval_seconds)

    print("Auto poll interval: {}s ({} min window / {} req/day, plan='{}')".format(
        interval_seconds, window_min, daily_limit, config.TRANSPORTAPI_PLAN))
    return interval_seconds

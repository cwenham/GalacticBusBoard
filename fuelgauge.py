"""
fuelgauge.py
─────────────────────────────────────────────────────────────────────────────
Optional LC709203F battery fuel gauge (e.g. Adafruit's breakout) on the
Galactic Unicorn's Qw/ST I2C connector. Detected automatically at boot; if
it isn't plugged in, every function here is a harmless no-op and the board
runs exactly as it would without this module.

Readings feed the battery-life log (see powerlog.py). Note the LC709203F
does NOT measure current — it has no sense resistor. Its state of charge is
a model estimate driven by cell voltage, so power draw has to be inferred
from how fast that estimate falls, and is only meaningful over windows of
an hour or so rather than heartbeat to heartbeat.

Register map, the CRC scheme and the pack-size (APA) and battery-profile
values all follow Adafruit's CircuitPython driver (adafruit_lc709203f.py),
checked against a real chip on this board.
─────────────────────────────────────────────────────────────────────────────
"""

import time
from machine import I2C, Pin

import config


# The Galactic Unicorn's Qw/ST connectors are wired to I2C0 on these pins.
# Fixed by the board's hardware, so not a user setting in config.py.
_I2C_ID  = 0
_SDA_PIN = 4
_SCL_PIN = 5
_I2C_FREQ = 100000   # the LC709203F is known to be finicky at faster bus speeds

_ADDR = 0x0B

_REG_INIT_RSOC    = 0x07
_REG_CELL_VOLTAGE = 0x09   # millivolts
_REG_APA          = 0x0B   # "adjustment pack application" — pack-size tuning
_REG_ITE          = 0x0F   # state of charge, 0.1% units (finer than RSOC's 1%)
_REG_IC_VERSION   = 0x11
_REG_PROFILE      = 0x12
_REG_POWER_MODE   = 0x15

_INIT_RSOC_MAGIC   = 0xAA55
_POWER_OPERATIONAL = 1
_PROFILE_4V2       = 1     # standard LiPo charged to 4.2V (Adafruit: "4.2V profile")

# APA register value for each pack capacity the chip is characterised for.
_APA_BY_MAH = {
    100: 0x08, 200: 0x0B, 400: 0x0E, 500: 0x10,
    1000: 0x19, 2000: 0x2D, 2200: 0x30, 3000: 0x36,
}

_i2c = None   # set only once the gauge has been detected and configured


def _crc8(data):
    """CRC-8, polynomial 0x07, init 0x00 — used on every read and write."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def _read(reg):
    """
    Read one 16-bit register, validating its CRC. Retries a couple of times
    because the chip can NACK while waking from its low-power state — the
    same allowance Adafruit's driver makes. Raises OSError if every attempt
    fails, so callers can decide whether that's fatal.
    """
    err = None
    for _ in range(3):
        try:
            lo, hi, crc = _i2c.readfrom_mem(_ADDR, reg, 3)
            if _crc8(bytes((_ADDR << 1, reg, (_ADDR << 1) | 1, lo, hi))) == crc:
                return (hi << 8) | lo
            err = OSError("CRC mismatch reading reg 0x{:02x}".format(reg))
        except OSError as exc:
            err = exc
        time.sleep_ms(100)
    raise err


def _write(reg, value):
    lo, hi = value & 0xFF, (value >> 8) & 0xFF
    crc = _crc8(bytes((_ADDR << 1, reg, lo, hi)))
    _i2c.writeto(_ADDR, bytes((reg, lo, hi, crc)))


def _write_verified(reg, value):
    """Write a register and read it back, so a silently dropped write can't
    leave the gauge half-configured while looking fine."""
    _write(reg, value)
    got = _read(reg)
    if got != value:
        raise OSError("reg 0x{:02x}: wrote 0x{:04x}, read back 0x{:04x}".format(reg, value, got))


def _apa_for(mah):
    """
    Return (APA value, exact) for the configured pack capacity.

    Packs above the largest characterised size — this board's own 13,400 mAh
    1S4P 18650 pack, for one — get the largest setting, with exact=False so
    the log can flag the resulting state of charge as approximate. As far as
    can be told, APA mainly corrects for the pack's voltage drop under load;
    at this board's draw spread across paralleled cells that drop is a few
    millivolts, so the mismatch likely costs less accuracy than it sounds.
    The logged cell voltage is a direct measurement and unaffected either way.
    """
    if mah in _APA_BY_MAH:
        return _APA_BY_MAH[mah], True
    largest = max(_APA_BY_MAH)
    if mah > largest:
        print("Fuel gauge: {} mAh is above the largest characterised pack ({} mAh);"
              " using that setting — soc is approximate, vbat is exact".format(mah, largest))
        return _APA_BY_MAH[largest], False
    nearest = min(_APA_BY_MAH, key=lambda k: abs(k - mah))
    print("Fuel gauge: no APA setting for {} mAh, using nearest ({} mAh)".format(mah, nearest))
    return _APA_BY_MAH[nearest], False


def _configure(want_apa):
    """
    Bring the gauge into a known-good state, disturbing it as little as
    possible. Returns "initialised" or "resumed".

    The chip keeps its own state independently of the Pico, so after a Pico
    reboot (a brownout mid-run, say) it may already be awake, correctly
    configured and partway through tracking the discharge. Re-initialising
    then would discard that tracking and re-estimate charge from voltage
    while the cell is under load, skewing everything logged afterwards.

    So charge is only re-estimated when it can't be trusted: the chip was
    asleep (it doesn't track while asleep — on this board it was found
    asleep reporting 91% on a freshly charged 4.2V cell), or its pack size
    or battery profile were wrong (every estimate made under the wrong
    settings is suspect).
    """
    was_asleep    = _read(_REG_POWER_MODE) != _POWER_OPERATIONAL
    misconfigured = (_read(_REG_APA) != want_apa or
                     _read(_REG_PROFILE) != _PROFILE_4V2)

    if was_asleep:
        _write_verified(_REG_POWER_MODE, _POWER_OPERATIONAL)
    if misconfigured:
        _write_verified(_REG_APA, want_apa)
        _write_verified(_REG_PROFILE, _PROFILE_4V2)

    if not (was_asleep or misconfigured):
        print("Fuel gauge: already tracking, left undisturbed")
        return "resumed"

    time.sleep_ms(100)
    _write(_REG_INIT_RSOC, _INIT_RSOC_MAGIC)   # write-only trigger; nothing to read back
    time.sleep_ms(100)
    print("Fuel gauge: configured for {} mAh, charge re-estimated from voltage".format(
        config.FUEL_GAUGE_PACK_MAH))
    return "initialised"


def init():
    """
    Detect and configure the gauge. Call once at boot, before WiFi comes up:
    re-estimating charge from voltage is most accurate with the cell at
    rest, and the WiFi radio is one of the board's bigger loads.

    Returns a short status for the boot log: "off" (disabled in config),
    "absent", "error", "initialised" or "resumed" — the last two suffixed
    with " soc=approx" when the pack is outside the chip's characterised
    range, so anyone reading the log later knows how far to trust the soc
    figures. Never raises — a missing or misbehaving gauge must never stop
    the bus board from running.
    """
    global _i2c

    if not config.FUEL_GAUGE_ENABLED:
        return "off"

    try:
        i2c = I2C(_I2C_ID, sda=Pin(_SDA_PIN), scl=Pin(_SCL_PIN), freq=_I2C_FREQ)
        if _ADDR not in i2c.scan():
            print("Fuel gauge: not detected")
            return "absent"
    except Exception as exc:
        print("Fuel gauge: I2C bus error (continuing without):", exc)
        return "absent"

    _i2c = i2c
    try:
        # A CRC-valid read confirms it really is an LC709203F answering,
        # not some other device that happens to sit at 0x0B.
        print("Fuel gauge: LC709203F detected, IC version 0x{:04x}".format(_read(_REG_IC_VERSION)))
        want_apa, exact = _apa_for(config.FUEL_GAUGE_PACK_MAH)
        status = _configure(want_apa)
        return status if exact else status + " soc=approx"
    except Exception as exc:
        print("Fuel gauge: setup failed (continuing without):", exc)
        _i2c = None
        return "error"


def describe():
    """
    Current readings as a log fragment, e.g. "vbat=4.216V soc=91.4%".
    Empty string if no gauge is in use; "gauge=read-failed" if one was
    detected but has stopped answering (a loose Qw/ST cable, say) — kept
    distinct from absence, so the log shows the difference.
    """
    if _i2c is None:
        return ""
    try:
        mv  = _read(_REG_CELL_VOLTAGE)
        ite = _read(_REG_ITE)
    except Exception as exc:
        print("Fuel gauge read failed:", exc)
        return "gauge=read-failed"
    return "vbat={:.3f}V soc={:.1f}%".format(mv / 1000, ite / 10)

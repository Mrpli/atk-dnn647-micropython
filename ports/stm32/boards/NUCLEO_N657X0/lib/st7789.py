"""
ST7789 1.9-inch TFT LCD driver for MicroPython (NUCLEO_N657X0).
Resolution: 170x320, 4-wire SPI, RGB565 color format.

Wiring (module → Nucleo N657X0 Arduino headers):
    GND   → GND
    VCC   → 3V3
    SCL   → D13  (PE15, SPI5_SCK)
    SDA   → D11  (PG2,  SPI5_MOSI)
    RESET → D8   (PD12)
    DC    → D9   (PD7)
    CS    → D10  (PA3,  SPI5_CS)
    BLK   → D7   (PE11) or 3V3

Usage:
    from machine import SPI, Pin
    import st7789

    spi = SPI(5, baudrate=40_000_000, polarity=0, phase=0)
    tft = st7789.ST7789(
        spi=spi,
        cs=Pin('D10'),
        dc=Pin('D9'),
        rst=Pin('D8'),
        blk=Pin('D7'),
        width=170,
        height=320,
        col_offset=35,
        row_offset=0,
    )

    tft.fill(0xF800)  # red
    tft.text("Hello", 10, 10, 0xFFFF)  # white text
    tft.show()  # flush framebuf to display
"""

import time
import framebuf
from machine import Pin

# ── Color constants (RGB565) ──────────────────────────────────────────────
BLACK       = 0x0000
WHITE       = 0xFFFF
RED         = 0xF800
GREEN       = 0x07E0
BLUE        = 0x001F
CYAN        = 0x07FF
MAGENTA     = 0xF81F
YELLOW      = 0xFFE0
ORANGE      = 0xFD20
GRAY        = 0x8410
DARKGRAY    = 0x4208

# ── ST7789 register definitions ───────────────────────────────────────────
_NOP        = 0x00
_SWRESET    = 0x01
_SLPIN      = 0x10
_SLPOUT     = 0x11
_NORON      = 0x13
_INVOFF     = 0x20
_INVON      = 0x21
_DISPON     = 0x29
_CASET      = 0x2A
_RASET      = 0x2B
_RAMWR      = 0x2C
_MADCTL     = 0x36
_COLMOD     = 0x3A

# ── Initialisation sequence for XL1.9 ST7789 170x320 ─────────────────────
_INIT_SEQUENCE = (
    # (register,       data_bytes,                  delay_ms)
    (0x11,             b'',                         120),      # sleep out
    (0x3A,             b'\x05',                     0),        # COLMOD: 16-bit / RGB565
    (0xC5,             b'\x1A',                     0),
    (0x36,             b'\x00',                     0),        # MADCTL: row/col order
    (0xB2,             b'\x05\x05\x00\x33\x33',     0),        # frame rate
    (0xB7,             b'\x05',                     0),
    (0xBB,             b'\x3F',                     0),        # VCOM
    (0xC0,             b'\x2C',                     0),        # power
    (0xC2,             b'\x01',                     0),
    (0xC3,             b'\x0F',                     0),
    (0xC4,             b'\x20',                     0),
    (0xC6,             b'\x01',                     0),
    (0xD0,             b'\xA4\xA1',                 0),
    (0xE8,             b'\x03',                     0),
    (0xE9,             b'\x09\x09\x08',             0),
    # positive gamma
    (0xE0,             b'\xD0\x05\x09\x09\x08\x14\x28\x33\x3F\x07\x13\x14\x28\x30', 0),
    # negative gamma
    (0xE1,             b'\xD0\x05\x09\x09\x08\x03\x24\x32\x32\x3B\x14\x13\x28\x2F', 0),
    (0x21,             b'',                         0),        # INVON (needed for this panel)
    (0x29,             b'',                         100),      # DISPON
)


class ST7789:
    """Driver for ST7789-based 1.9\" 170x320 TFT over 4-wire SPI."""

    def __init__(self, spi, cs, dc, rst=None, blk=None,
                 width=170, height=320, col_offset=35, row_offset=0):
        """
        :param spi:         machine.SPI instance (SPI5 recommended).
        :param cs:          machine.Pin for Chip Select.
        :param dc:          machine.Pin for Data/Command.
        :param rst:         machine.Pin for Reset (optional but recommended).
        :param blk:         machine.Pin for Backlight (optional).
        :param width:       Display width in pixels (default 170).
        :param height:      Display height in pixels (default 320).
        :param col_offset:  Column address offset (35 for this panel).
        :param row_offset:  Row address offset (0 for this panel).
        """
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.blk = blk
        self.width = width
        self.height = height
        self.col_offset = col_offset
        self.row_offset = row_offset

        # Initialise control pins
        self.cs.init(mode=Pin.OUT, value=1)
        self.dc.init(mode=Pin.OUT, value=0)
        if self.rst:
            self.rst.init(mode=Pin.OUT, value=1)
        if self.blk:
            self.blk.init(mode=Pin.OUT, value=0)

        # Hardware reset
        self._reset()

        # Send init sequence
        self._init()

        # Create frame buffer: 170 * 320 pixels * 2 bytes/pixel = 108,800 bytes
        # Use RGB565 format for direct blit to the display.
        self.buf = bytearray(self.width * self.height * 2)
        self.fb = framebuf.FrameBuffer(self.buf, self.width, self.height,
                                       framebuf.RGB565)

        # Default scan direction: portrait (0,0 at top-left)
        self._rotation = 0

        # Fill black
        self.fill(BLACK)
        self.show()

    # ── Low-level SPI helpers ─────────────────────────────────────────

    def _write_cmd(self, cmd):
        """Send a command byte (DC low)."""
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def _write_data(self, data):
        """Send data bytes (DC high)."""
        if data:
            self.dc(1)
            self.cs(0)
            self.spi.write(data if isinstance(data, bytes) else bytearray(data))
            self.cs(1)

    def _reset(self):
        """Hardware reset the controller."""
        if not self.rst:
            return
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(120)

    def _init(self):
        """Send the manufacturer-provided initialisation sequence."""
        if self.blk:
            self.blk(1)  # backlight on
        time.sleep_ms(100)

        for reg, data, delay in _INIT_SEQUENCE:
            self._write_cmd(reg)
            if data:
                self._write_data(data)
            if delay:
                time.sleep_ms(delay)

    # ── Addressing ────────────────────────────────────────────────────

    def _set_window(self, x0, y0, x1, y1):
        """Set the column and row address window for subsequent writes."""
        x0 += self.col_offset
        x1 += self.col_offset
        y0 += self.row_offset
        y1 += self.row_offset

        self._write_cmd(_CASET)
        self._write_data(bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))

        self._write_cmd(_RASET)
        self._write_data(bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))

        self._write_cmd(_RAMWR)

    # ── Public drawing API ────────────────────────────────────────────

    def show(self):
        """Flush the entire framebuffer to the display."""
        self._set_window(0, 0, self.width - 1, self.height - 1)
        self.dc(1)
        self.cs(0)
        self.spi.write(self.buf)
        self.cs(1)

    def show_region(self, x, y, w, h):
        """Flush a rectangular region of the framebuffer.

        Useful for partial updates.  ``x``, ``y``, ``w``, ``h`` must be
        within [0, self.width) / [0, self.height).
        """
        self._set_window(x, y, x + w - 1, y + h - 1)
        self.dc(1)
        self.cs(0)
        # Walk each row of the region and send the slice.
        for row in range(y, y + h):
            start = (row * self.width + x) * 2
            self.spi.write(self.buf[start:start + w * 2])
        self.cs(1)

    # ── Delegated framebuf methods ────────────────────────────────────

    def fill(self, color=BLACK):
        self.fb.fill(color)

    def pixel(self, x, y, color):
        self.fb.pixel(x, y, color)

    def hline(self, x, y, w, color):
        self.fb.hline(x, y, w, color)

    def vline(self, x, y, h, color):
        self.fb.vline(x, y, h, color)

    def line(self, x0, y0, x1, y1, color):
        self.fb.line(x0, y0, x1, y1, color)

    def rect(self, x, y, w, h, color, fill=False):
        self.fb.rect(x, y, w, h, color, fill)

    def ellipse(self, x, y, rx, ry, color, fill=False):
        self.fb.ellipse(x, y, rx, ry, color, fill)

    def text(self, text, x, y, color=WHITE):
        self.fb.text(text, x, y, color)

    def blit(self, fbuf, x, y, key=-1):
        """Copy another framebuf (or the display's own fb) to position (x,y).

        ``key`` is the transparent color (default -1 = no transparency).
        """
        self.fb.blit(fbuf, x, y, key)

    # ── Rotation ──────────────────────────────────────────────────────

    @property
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, val):
        """Set display rotation: 0=portrait, 1=landscape, 2=reverse portrait, 3=reverse landscape."""
        madctl_map = {
            0: 0x00,   # portrait
            1: 0x60,   # landscape (MY=0, MX=1, MV=1)
            2: 0xC0,   # reverse portrait (MY=1, MX=1)
            3: 0xA0,   # reverse landscape (MY=1, MV=1)
        }
        self._write_cmd(_MADCTL)
        self._write_data(bytes([madctl_map.get(val, 0x00)]))
        self._rotation = val

    # ── Convenience ────────────────────────────────────────────────────

    def sleep(self, enable=True):
        """Enter (True) or exit (False) sleep mode."""
        self._write_cmd(_SLPIN if enable else _SLPOUT)
        if not enable:
            time.sleep_ms(120)

    def invert(self, enable=True):
        """Enable or disable display colour inversion."""
        self._write_cmd(_INVON if enable else _INVOFF)

    def brightness(self, value=None):
        """Get/set backlight. ``value``: 0=off, 1=on (GPIO control only)."""
        if self.blk is None:
            return None
        if value is None:
            return self.blk()
        self.blk(1 if value else 0)
        return value

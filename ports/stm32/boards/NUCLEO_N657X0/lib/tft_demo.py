"""
Demo script for the ST7789 1.9" TFT on NUCLEO_N657X0.

Wiring (module → Nucleo Arduino headers):
    GND   → GND       SCL   → D13 (SPI5_SCK)
    VCC   → 3V3       SDA   → D11 (SPI5_MOSI)
    RESET → D8        DC    → D9
    CS    → D10       BLK   → D7 (or 3V3)

Copy st7789.py to the board first, then run this script.
"""

from machine import SPI, Pin
import st7789
import time

# ── Initialise the display ────────────────────────────────────────────────
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

print(f"Display initialised: {tft.width}x{tft.height}")
print(f"SPI freq: {spi.baudrate // 1_000_000} MHz")

# ── Demo 1: Color bars ───────────────────────────────────────────────────
print("Demo 1: Color fill test")
colors = [
    (st7789.RED,    "RED"),
    (st7789.GREEN,  "GREEN"),
    (st7789.BLUE,   "BLUE"),
    (st7789.WHITE,  "WHITE"),
    (st7789.BLACK,  "BLACK"),
]
for color, name in colors:
    tft.fill(color)
    tft.text(name, 5, 5, st7789.WHITE if color != st7789.WHITE else st7789.BLACK)
    tft.show()
    time.sleep_ms(500)

# ── Demo 2: Geometric shapes ─────────────────────────────────────────────
print("Demo 2: Shapes")
tft.fill(st7789.BLACK)

tft.rect(5, 5, 40, 40, st7789.RED)          # red outline
tft.rect(50, 5, 40, 40, st7789.GREEN, True)  # green filled
tft.ellipse(115, 25, 20, 20, st7789.BLUE, True)  # blue circle
tft.line(5, 60, 160, 60, st7789.YELLOW)      # horizontal line
tft.line(5, 65, 160, 90, st7789.CYAN)        # diagonal line
tft.hline(5, 100, 160, st7789.MAGENTA)
tft.vline(85, 5, 50, st7789.ORANGE)

tft.text("Hello ST7789!", 5, 120, st7789.WHITE)
tft.text("NUCLEO-N657X0", 5, 140, st7789.GREEN)
tft.text("MicroPython", 5, 160, st7789.YELLOW)

tft.show()
time.sleep_ms(2000)

# ── Demo 3: Rotary effect ────────────────────────────────────────────────
print("Demo 3: Rotation test")
for rot in range(4):
    tft.fill(st7789.BLACK)
    tft.rotation = rot
    tft.text(f"Rotation: {rot}", 5, 5, st7789.WHITE)
    tft.rect(10, 30, 50, 50, st7789.RED, True)
    tft.show()
    time.sleep_ms(1000)

# Reset to portrait
tft.rotation = 0

# ── Demo 4: Partial update (faster) ──────────────────────────────────────
print("Demo 4: Partial update")
tft.fill(st7789.BLACK)
tft.show()

# Only update a small region
for i in range(10):
    x = (i * 15) % (tft.width - 30)
    tft.rect(x, 140, 30, 30, st7789.BLACK, True)   # clear in fb
    tft.text(str(i), x + 10, 148, st7789.WHITE)      # draw in fb
    tft.show_region(x, 140, 30, 30)                   # only flush this region
    time.sleep_ms(100)

print("Demo complete!")

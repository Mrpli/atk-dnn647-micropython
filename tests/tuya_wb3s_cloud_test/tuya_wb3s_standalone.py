# -*- coding: utf-8 -*-
"""
WB3S AT 固件云端测试 — 单文件独立版
====================================

将此文件重命名为 main.py 并复制到 MicroPython 板子:
    mpremote cp tuya_wb3s_standalone.py :main.py
    mpremote reset

硬件接线 (Nucleo-N657X0 <-> XH-WB3S):
    N657 D1 (PD8)  ->  WB3S RXD1 (pin 21)
    N657 D0 (PD9)  ->  WB3S TXD1 (pin 22)
    N657 D2 (PD0)  ->  WB3S CEN  (pin 1, 复位)
    N657 3.3V      ->  WB3S VCC  (pin 8)
    N657 GND       ->  WB3S GND  (pin 15)

使用前请修改下方配置区的 WIFI_SSID 和 WIFI_PASSWORD!
"""

import time
from machine import UART, Pin


# =============================================================================
# 配置区 - 使用前请修改!
# =============================================================================

WIFI_SSID = "your_wifi_ssid"  # WiFi 名称 (2.4GHz)
WIFI_PASSWORD = "your_wifi_password"  # WiFi 密码
CLOUD_HOST = "115.29.109.104"  # 云端服务器地址
CLOUD_PORT = 6602  # 云端服务器端口
WB3S_BAUD = 115200  # AT 固件默认 115200
RST_PIN = "D2"  # CEN 复位引脚 (None=不用)
DEBUG = True  # 调试输出
REPORT_SEC = 10  # 上报间隔秒数


# =============================================================================
# LED 和按键
# =============================================================================

try:
    LED_RED = Pin("LED_RED", Pin.OUT, value=1)
    LED_GREEN = Pin("LED_GREEN", Pin.OUT, value=1)
    LED_BLUE = Pin("LED_BLUE", Pin.OUT, value=1)
    BUTTON = Pin("BUTTON", Pin.IN, Pin.PULL_DOWN)
except Exception:
    LED_RED = LED_GREEN = LED_BLUE = BUTTON = None


def _on(led):
    if led:
        led.low()


def _off(led):
    if led:
        led.high()


def _blink(led, n=3, t=0.1):
    if led is None:
        return
    for _ in range(n):
        led.low()
        time.sleep(t)
        led.high()
        time.sleep(t)


# =============================================================================
# WB3S AT 驱动 (精简版)
# =============================================================================


class WB3S:
    """WB3S AT 命令驱动 (BK7238 AT 固件)"""

    OK = "OK"
    ERROR = "ERROR"

    def __init__(self, uart_id=3, tx="D1", rx="D0", rst=None, baud=115200, dbg=False):
        self.dbg = dbg
        self._transparent = False
        self._uart = UART(
            uart_id,
            baudrate=baud,
            bits=8,
            parity=None,
            stop=1,
            tx=Pin(tx),
            rx=Pin(rx),
            timeout=100,
            timeout_char=20,
            read_buf_len=1024,
        )
        self._rst = Pin(rst, Pin.OUT, value=1) if rst else None

    def _log(self, s):
        if self.dbg:
            print(f"[WB3S] {s}")

    def reset(self, delay=1.5):
        """硬件复位 (CEN 拉低 ≥300ms)"""
        if not self._rst:
            return False
        self._log("硬件复位...")
        self._uart.read()
        self._rst.low()
        time.sleep(0.35)
        self._rst.high()
        time.sleep(delay)
        self._transparent = False
        return True

    def _cmd(self, cmd, timeout=3000, end="OK\r\n"):
        """发送 AT 命令, 返回清洗后的响应文本"""
        if self._transparent:
            self._log("警告: 透传中, 请先退出")
            return ""

        self._uart.write(cmd + "\r\n")
        self._log(f"TX: {cmd}")

        buf = bytearray()
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout:
            if self._uart.any():
                buf.extend(self._uart.read(self._uart.any()))
                txt = buf.decode("ascii", errors="ignore")
                if end in txt or (end == ">" and ">" in txt):
                    break
            time.sleep_ms(5)

        text = buf.decode("ascii", errors="ignore")
        # 清洗: 去回显和空行
        lines = [l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
        lines = [l for l in lines if l != cmd.strip()]
        clean = "\n".join(lines)
        self._log(f"RX: {clean[:200]}")
        return clean

    def wait_ready(self, timeout=10):
        """等待模块启动 (ready 提示)"""
        self._uart.read()
        buf = bytearray()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self._uart.any():
                buf.extend(self._uart.read(self._uart.any()))
                if b"ready" in buf:
                    self._log("模块就绪")
                    return True
            time.sleep_ms(50)
        return False

    def test(self):
        """AT 通信测试"""
        return self.OK in self._cmd("AT", timeout=1000)

    def get_version(self):
        return self._cmd("AT+GMR", timeout=1000)

    # ---- WiFi ----

    def connect_wifi(self, ssid, pwd, timeout=20000):
        """连接 WiFi, 返回 True/False"""
        self._log(f"WiFi: {ssid}")
        self._cmd("AT+CWMODE=1", timeout=500)
        time.sleep(0.3)
        resp = self._cmd(f'AT+CWJAP="{ssid}","{pwd}"', timeout=timeout)
        return self.OK in resp or "WIFI CONNECTED" in resp or "WIFI GOT IP" in resp

    def get_ip(self):
        return self._cmd("AT+CIFSR", timeout=1000)

    def scan_wifi(self, timeout=10000):
        return self._cmd("AT+CWLAP", timeout=timeout)

    # ---- TCP Client ----

    def tcp_connect(self, host, port, timeout=15000):
        """连接 TCP 服务器"""
        self._cmd("AT+CIPMUX=0", timeout=500)
        time.sleep(0.1)
        self._cmd("AT+CIPMODE=0", timeout=500)
        time.sleep(0.1)
        resp = self._cmd(f'AT+CIPSTART="TCP","{host}",{port}', timeout=timeout)
        if "CONNECT" in resp or "ALREADY CONNECTED" in resp:
            return True
        return False

    def tcp_send(self, data, timeout=5000):
        """发送 TCP 数据 (非透传)"""
        if isinstance(data, str):
            data = data.encode("utf-8")
        resp = self._cmd(f"AT+CIPSEND={len(data)}", timeout=2000, end=">")
        if ">" not in resp:
            return False
        self._uart.write(data)
        # 等待结果
        buf = bytearray()
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout:
            if self._uart.any():
                buf.extend(self._uart.read(self._uart.any()))
                if b"SEND OK" in buf:
                    return True
                if b"ERROR" in buf:
                    return False
            time.sleep_ms(10)
        return False

    def tcp_close(self):
        self._transparent = False
        return self._cmd("AT+CIPCLOSE", timeout=3000)

    # ---- 透传模式 ----

    def transparent_connect(self, host, port, timeout=15000):
        """进入 TCP 透传模式"""
        self._cmd("AT+CIPMUX=0", timeout=500)
        time.sleep(0.1)
        self._cmd("AT+CIPMODE=1", timeout=500)
        time.sleep(0.1)
        resp = self._cmd(f'AT+CIPSTART="TCP","{host}",{port}', timeout=timeout, end="CONNECT")
        if "CONNECT" in resp:
            self._transparent = True
            self._cmd("AT+CIPSEND", timeout=2000, end=">")
            return True
        return False

    def send_raw(self, data):
        """透传发送"""
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._uart.write(data)
        return True

    def recv_raw(self, timeout=200):
        """透传接收"""
        if self._uart.any():
            return self._uart.read(self._uart.any())
        return None

    def exit_transparent(self):
        """退出透传"""
        if not self._transparent:
            return True
        time.sleep(1.0)
        self._uart.write("+++")
        time.sleep(0.5)
        self._transparent = False
        return True

    # ---- 配网 & 其他 ----

    def smart_config(self, enable=True):
        return self._cmd(f"AT+BLUFI={1 if enable else 0}", timeout=2000)

    def set_ap(self, ssid, pwd, ch=11, enc=3):
        self._cmd("AT+CWMODE=2", timeout=500)
        time.sleep(0.2)
        return self._cmd(f'AT+CWSAP="{ssid}","{pwd}",{ch},{enc}', timeout=1000)

    def tcp_server_start(self, port=8080):
        self._cmd("AT+CIPMUX=1", timeout=500)
        time.sleep(0.2)
        return self.OK in self._cmd(f"AT+CIPSERVER=1,{port}", timeout=2000)

    def tcp_server_stop(self):
        return self._cmd("AT+CIPSERVER=0", timeout=2000)

    def restore(self):
        return self._cmd("AT+RESTORE", timeout=5000)

    def close(self):
        if self._transparent:
            self.exit_transparent()
        self._uart.deinit()


# =============================================================================
# 测试程序
# =============================================================================


def quick_test():
    """快速连通性测试"""
    print("==== WB3S 快速连通性测试 ====")

    wb3s = WB3S(uart_id=3, tx="D1", rx="D0", rst=RST_PIN, baud=WB3S_BAUD, dbg=DEBUG)

    if RST_PIN:
        wb3s.reset(2.0)
        wb3s.wait_ready(10)

    # AT 测试
    print("[1] AT 通信测试...")
    if wb3s.test():
        print("  ✓ OK")
    else:
        print("  ✗ 失败: 检查接线 / 波特率 / 供电")
        wb3s.close()
        return

    # 版本
    print("[2] 固件版本:")
    print(f"  {wb3s.get_version()}")

    # 扫描 WiFi
    print("[3] 附近 WiFi:")
    try:
        aps = wb3s.scan_wifi(8000)
        for line in aps.split("\n")[:5]:
            print(f"  {line.strip()}")
    except Exception:
        pass

    print("\n✓ 快速测试通过!")
    wb3s.close()


def cloud_report_test():
    """TCP Client 周期上报云端"""
    print("==== WB3S 云端上报测试 ====")

    wb3s = WB3S(uart_id=3, tx="D1", rx="D0", rst=RST_PIN, baud=WB3S_BAUD, dbg=DEBUG)

    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    # 连接 WiFi
    print("\n连接 WiFi...")
    _blink(LED_BLUE, 2)
    if not wb3s.connect_wifi(WIFI_SSID, WIFI_PASSWORD, timeout=20000):
        print("✗ WiFi 失败")
        _blink(LED_RED, 5)
        wb3s.close()
        return
    print("✓ WiFi OK")
    _on(LED_BLUE)

    # 上报循环
    print(f"\n上报到 {CLOUD_HOST}:{CLOUD_PORT} (间隔 {REPORT_SEC}s)")
    _on(LED_GREEN)
    last, cnt = 0, 0

    try:
        while True:
            now = time.time()
            btn = BUTTON and BUTTON.value() == 1

            if (now - last >= REPORT_SEC) or btn:
                if btn:
                    print("\n[BTN] 手动触发")
                    time.sleep_ms(200)

                last = now
                cnt += 1
                import random

                temp = 250 + random.randint(-30, 30)
                hum = 600 + random.randint(-60, 60)
                data = f'{{"dev":"N657-WB3S","id":{cnt},"temp":{temp / 10:.1f},"hum":{hum / 10:.1f}}}\r\n'

                print(f"\n[{cnt}] T={temp / 10:.1f}°C H={hum / 10:.1f}%")
                print(f"     JSON: {data.strip()}")

                if wb3s.tcp_connect(CLOUD_HOST, CLOUD_PORT, timeout=10000):
                    if wb3s.tcp_send(data):
                        print("     ✓ 发送成功")
                        _blink(LED_GREEN, 1)
                    else:
                        print("     ✗ 发送失败")
                    wb3s.tcp_close()
                else:
                    print("     ✗ 连接失败")
                    _blink(LED_RED, 3)

            time.sleep_ms(200)

    except KeyboardInterrupt:
        print("\n中断")

    wb3s.tcp_close()
    _off(LED_GREEN)
    _off(LED_BLUE)
    wb3s.close()
    print("结束")


def transparent_test():
    """透传模式测试"""
    print("==== WB3S 透传模式 ====")

    wb3s = WB3S(uart_id=3, tx="D1", rx="D0", rst=RST_PIN, baud=WB3S_BAUD, dbg=DEBUG)

    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    if not wb3s.connect_wifi(WIFI_SSID, WIFI_PASSWORD, timeout=20000):
        print("✗ WiFi 失败")
        wb3s.close()
        return

    print(f"进入透传 -> {CLOUD_HOST}:{CLOUD_PORT}")
    if not wb3s.transparent_connect(CLOUD_HOST, CLOUD_PORT, timeout=15000):
        print("✗ 连接失败")
        wb3s.close()
        return

    print("✓ 透传中 (发送 '+++' 退出)")
    _on(LED_GREEN)

    cnt = 0
    try:
        while True:
            cnt += 1
            data = f"TRANS-{cnt} TEMP={25 + cnt % 5}.{cnt % 10}C\r\n"
            wb3s.send_raw(data)
            print(f"[{cnt}] {data.strip()}")

            resp = wb3s.recv_raw(100)
            if resp:
                print(f"  <- {resp.decode('utf-8', errors='ignore')[:80]}")

            time.sleep(REPORT_SEC)
    except KeyboardInterrupt:
        print("\n退出透传...")
        wb3s.exit_transparent()

    wb3s.close()
    print("结束")


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    # ------ 选择模式 ------
    MODE = 1
    # 1 = 快速连通性测试 (推荐先跑)
    # 2 = TCP Client 云端周期上报
    # 3 = 透传模式
    # --------------------

    if MODE == 1:
        quick_test()
    elif MODE == 2:
        cloud_report_test()
    elif MODE == 3:
        transparent_test()

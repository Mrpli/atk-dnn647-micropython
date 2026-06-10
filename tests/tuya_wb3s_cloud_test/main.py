"""
WB3S AT 固件 — 云端数据发送测试 (Nucleo-N657X0)
================================================

针对 XH-WB3S (BK7238) AT 固件的云端数据通信测试。
兼容 ESP8266 风格 AT 指令集。

使用方法:
    1. 修改下方 WiFi 和服务器配置
    2. mpremote cp wb3s_at.py :wb3s_at.py
    3. mpremote cp main.py :main.py
    4. mpremote reset

硬件接线:
    N657 D1 (PD8)  -> WB3S RXD1 (pin 21)
    N657 D0 (PD9)  -> WB3S TXD1 (pin 22)
    N657 D2 (PD0)  -> WB3S CEN  (pin 1, 复位, 低电平有效)
    N657 3.3V      -> WB3S VCC  (pin 8)
    N657 GND       -> WB3S GND  (pin 15)
"""

import time
from machine import Pin
from wb3s_at import WB3S

# =============================================================================
# 用户配置 — 请根据实际情况修改
# =============================================================================

# WiFi 配置
WIFI_SSID = "kfcvivo50"  # WiFi 名称 (2.4GHz)
WIFI_PASSWORD = "50505050"  # WiFi 密码

# 云端 TCP 服务器配置
# 可以用网上免费的 TCP 测试服务器, 如 http://tcp.doit.am/
# 也可以自己搭建 (用 nc -l 8080 或 Python TCP server)
CLOUD_HOST = "115.29.109.104"  # 云端服务器地址
CLOUD_PORT = 6602  # 云端服务器端口

# WB3S 通信参数
WB3S_UART_ID = 3  # UART3 (D1=TX=PD8, D0=RX=PD9)
WB3S_BAUD = 115200  # AT 固件默认 115200
RST_PIN = "D2"  # CEN 复位引脚 (None 表示不用)
DEBUG = True

# 上报间隔 (秒)
REPORT_INTERVAL = 10


# =============================================================================
# LED 和按键
# =============================================================================

try:
    LED_RED = Pin("LED_RED", Pin.OUT, value=1)  # 高电平灭, 低电平亮
    LED_GREEN = Pin("LED_GREEN", Pin.OUT, value=1)
    LED_BLUE = Pin("LED_BLUE", Pin.OUT, value=1)
    BUTTON = Pin("BUTTON", Pin.IN, Pin.PULL_DOWN)
except Exception:
    LED_RED = LED_GREEN = LED_BLUE = BUTTON = None


def led_on(led):
    if led:
        led.low()


def led_off(led):
    if led:
        led.high()


def led_blink(led, times=3, interval=0.1):
    if led is None:
        return
    for _ in range(times):
        led.low()
        time.sleep(interval)
        led.high()
        time.sleep(interval)


# =============================================================================
# 测试 1: 快速连通性测试
# =============================================================================


def quick_test():
    """
    快速测试: 验证 WB3S 硬件连接和 AT 通信是否正常。
    测试流程: 复位 → 等待 ready → AT 测试 → 查询版本
    """
    print("=" * 50)
    print("  WB3S 快速连通性测试")
    print("=" * 50)

    wb3s = WB3S(
        uart_id=WB3S_UART_ID,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=RST_PIN,
        baudrate=WB3S_BAUD,
        debug=DEBUG,
    )

    # 1. 硬件复位
    print("\n[1] 硬件复位...")
    if RST_PIN:
        wb3s.reset(delay=2.0)
        # 等待 ready 信号
        if wb3s.wait_ready(timeout=10):
            print("  ✓ 模块启动成功 (收到 ready)")
        else:
            print("  未收到 ready 但有可能是超时")
    else:
        print("  RST 引脚未配置, 请手动复位模块")

    # 2. AT 通信测试
    print("\n[2] AT 通信测试...")
    if wb3s.at_test():
        print("  ✓ AT 通信正常")
    else:
        print("  ✗ AT 通信失败! 请检查:")
        print("    1. 接线: D1(PD8)->WB3S RXD1, D0(PD9)->WB3S TXD1")
        print("    2. 供电: 3.3V / ≥500mA")
        print("    3. 波特率: 115200, 8N1")
        wb3s.close()
        return

    # 3. 查询固件版本
    print("\n[3] 固件信息:")
    ver = wb3s.get_version()
    print(f"  {ver}")

    # 4. 查询芯片 ID
    chip = wb3s.get_chip_id()
    if chip:
        print(f"  {chip}")

    # 5. 扫描 WiFi
    print("\n[4] 扫描附近 WiFi (前5个)...")
    try:
        ap_list = wb3s.scan_wifi(timeout=8000)
        lines = ap_list.split("\n")[:5]
        for line in lines:
            print(f"  {line.strip()}")
    except Exception:
        pass

    print("\n✓ 快速测试通过! 硬件连接正常.")
    wb3s.close()


# =============================================================================
# 测试 2: TCP Client 模式周期上报
# =============================================================================


def tcp_client_test():
    """
    TCP Client 模式: 连 WiFi → 连云端 → 周期性发送 JSON 数据。

    适用场景:
        - 自己搭建的 TCP 服务器 (Python nc / netcat)
        - 云端的 MQTT broker (需要 MQTT 协议封装)
        - 任何接收 TCP 数据的云平台
    """
    print("=" * 50)
    print("  WB3S TCP Client 云端发送测试")
    print("=" * 50)

    wb3s = WB3S(
        uart_id=WB3S_UART_ID,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=RST_PIN,
        baudrate=WB3S_BAUD,
        debug=DEBUG,
    )

    # 复位
    print("\n[1/4] 复位模块...")
    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    # 连接 WiFi
    print("\n[2/4] 连接 WiFi...")
    led_blink(LED_BLUE, 2, 0.2)

    if not wb3s.connect_wifi(WIFI_SSID, WIFI_PASSWORD, timeout=20000):
        print("  ✗ WiFi 连接失败! 请检查 SSID/密码/2.4GHz")
        print("  提示: 可尝试智能配网模式 (smart_config_test)")
        led_blink(LED_RED, 5, 0.2)
        wb3s.close()
        return

    led_on(LED_BLUE)
    print("  ✓ WiFi 已连接")
    ip_info = wb3s.get_ip()
    print(f"  IP 信息:\n{ip_info}")

    # 主循环
    print(f"\n[3/4] 开始上报 (间隔={REPORT_INTERVAL}s)")
    print(f"  目标: {CLOUD_HOST}:{CLOUD_PORT}")
    print("  按 USER 键手动触发")
    print("-" * 50)

    led_on(LED_GREEN)
    last_report = 0
    counter = 0

    try:
        while True:
            now = time.time()
            btn = BUTTON and BUTTON.value() == 1

            if (now - last_report >= REPORT_INTERVAL) or btn:
                if btn:
                    print("\n[BTN] 手动触发")
                    time.sleep_ms(200)

                last_report = now
                counter += 1

                # ---- 模拟传感器数据 ----
                import random

                temp = 250 + random.randint(-30, 30)  # 温度 ×10
                hum = 600 + random.randint(-60, 60)  # 湿度 ×10

                # 构造 JSON 上报数据
                data = (
                    '{{"device":"N657-WB3S","id":{},"temp":{:.1f},"hum":{:.1f},"time":{}}}\r\n'
                ).format(counter, temp / 10.0, hum / 10.0, int(now))

                print(f"\n  --- 第 {counter} 次上报 ---")
                print(f"  温度: {temp / 10:.1f}°C  湿度: {hum / 10:.1f}%")
                print(f"  JSON: {data.strip()}")

                # ---- 连接服务器 → 发送 → 关闭 ----
                if wb3s.tcp_connect(CLOUD_HOST, CLOUD_PORT, timeout=10000):
                    if wb3s.tcp_send(data, timeout=3000):
                        print("  ✓ 发送成功")
                        led_blink(LED_GREEN, 1, 0.1)
                    else:
                        print("  ✗ 发送失败")
                        led_blink(LED_RED, 1, 0.1)

                    # 可选: 接收服务器返回
                    time.sleep_ms(100)
                    resp = wb3s.tcp_recv(timeout=300)
                    if resp:
                        print(f"  回复: {resp.decode('utf-8', errors='ignore')[:100]}")

                    wb3s.tcp_close()
                else:
                    print("  ✗ 服务器连接失败")
                    led_blink(LED_RED, 3, 0.1)

                print("-" * 50)

            time.sleep_ms(200)

    except KeyboardInterrupt:
        print("\n\n用户中断")

    print("\n[4/4] 清理...")
    wb3s.tcp_close()
    led_off(LED_GREEN)
    led_off(LED_BLUE)
    wb3s.close()
    print("测试结束")


# =============================================================================
# 测试 3: 透传模式 (高效持续发送)
# =============================================================================


def transparent_mode_test():
    """
    透传模式: 建立 TCP 后直接收发原始数据, 无需每次 AT 命令包裹。

    优点: 低延迟, 高效率, 适合持续数据流
    退出: 发送 '+++' (不带换行)
    """
    print("=" * 50)
    print("  WB3S 透传模式测试")
    print("=" * 50)

    wb3s = WB3S(
        uart_id=WB3S_UART_ID,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=RST_PIN,
        baudrate=WB3S_BAUD,
        debug=DEBUG,
    )

    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    # 连 WiFi
    print("\n[1] 连接 WiFi...")
    if not wb3s.connect_wifi(WIFI_SSID, WIFI_PASSWORD, timeout=20000):
        print("  ✗ WiFi 连接失败")
        wb3s.close()
        return
    print("  ✓ WiFi 已连接")

    # 透传连接
    print(f"\n[2] 进入透传模式 -> {CLOUD_HOST}:{CLOUD_PORT}")
    print("  提示: 发送 '+++' 退出透传")
    if not wb3s.transparent_connect(CLOUD_HOST, CLOUD_PORT, timeout=15000):
        print("  ✗ 透传连接失败")
        wb3s.close()
        return

    print("  ✓ 已进入透传模式")
    led_on(LED_GREEN)

    # 透传发送循环
    counter = 0
    try:
        while True:
            counter += 1
            # 直接发送原始数据
            data = "TRANS-{} TEMP={:.1f}C HUM={:.1f}%\n".format(
                counter, 25.0 + counter % 5, 60.0 + counter % 10
            )
            wb3s.send_raw(data)
            print(f"  [{counter}] {data.strip()}")

            # 检查返回
            resp = wb3s.recv_raw(timeout=100)
            if resp:
                print(f"  收到: {resp.decode('utf-8', errors='ignore')[:80]}")

            time.sleep(REPORT_INTERVAL)

    except KeyboardInterrupt:
        print("\n退出透传...")
        wb3s.exit_transparent()

    wb3s.close()
    print("测试结束")


# =============================================================================
# 测试 4: 智能配网 (SmartConfig / BLUFI)
# =============================================================================


def smart_config_test():
    """
    智能配网: 首次使用时, 通过手机 App 将 WiFi 凭据发送给 WB3S。

    步骤:
        1. 运行此程序
        2. 手机上安装乐鑫 ESP-BLUFI App
        3. 在 App 中输入 2.4GHz WiFi SSID/密码
        4. 靠近模块, 点击发送
        5. 模块自动连接 WiFi
    """
    print("=" * 50)
    print("  WB3S 智能配网 (SmartConfig/BLUFI)")
    print("=" * 50)

    wb3s = WB3S(
        uart_id=WB3S_UART_ID,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=RST_PIN,
        baudrate=WB3S_BAUD,
        debug=DEBUG,
    )

    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    # 检查是否已连接
    print("\n[1] 检查当前网络...")
    ip = wb3s.get_ip()
    print(f"  {ip}")

    has_ip = any(
        line
        and ("STAIP" in line or "IP" in line)
        and any(net in line for net in ("192.", "10.", "172."))
        for line in ip.split("\n")
    )

    if has_ip:
        print("  ✓ WiFi 已连接, 无需配网")
    else:
        print("\n[2] 进入智能配网...")
        print("  >>> 手机安装 'ESP-BLUFI' App <<<")
        print("  >>> 输入 WiFi SSID/密码, 靠近模块 <<<")

        wb3s.smart_config(enable=True)

        print("  等待配网 (最长 90s)...")
        start = time.time()
        connected = False
        while time.time() - start < 90:
            ip = wb3s.get_ip()
            for line in ip.split("\n"):
                if "STAIP" in line:
                    addr = line.split('"')[1] if '"' in line else line.split(":")[-1].strip()
                    if addr and addr != "0.0.0.0" and addr.startswith(("192.", "10.", "172.")):
                        connected = True
                        print(f"\n  ✓ 配网成功! IP: {addr}")
                        break
            if connected:
                break
            led_blink(LED_BLUE, 1, 0.3)
            time.sleep(3)

        if not connected:
            print("\n  ✗ 配网超时")
            print("  提示: 1) 确保 2.4GHz WiFi  2) 手机靠近模块")
            print("        3) 尝试 AT+RESTORE 恢复出厂")
            led_blink(LED_RED, 5, 0.2)

    print(f"\n[3] 最终状态:\n{wb3s.get_ip()}")
    wb3s.close()


# =============================================================================
# 测试 5: TCP Server 模式 (手机连模块)
# =============================================================================


def tcp_server_test():
    """
    TCP Server 模式: WB3S 开启 AP 热点 + TCP 服务器。
    手机/电脑连接模块热点后进行数据收发。
    """
    print("=" * 50)
    print("  WB3S TCP Server 模式")
    print("=" * 50)

    wb3s = WB3S(
        uart_id=WB3S_UART_ID,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=RST_PIN,
        baudrate=WB3S_BAUD,
        debug=DEBUG,
    )

    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    # 开启 AP 热点
    print("\n[1] 开启 AP 热点: N657-WB3S / 12345678")
    wb3s.set_ap("N657-WB3S", "12345678", channel=11, encryption=3)
    time.sleep(1)
    print(f"  模块 IP: 192.168.4.1")

    # 启动 TCP Server
    print("\n[2] 启动 TCP Server (端口 8080)...")
    if wb3s.tcp_server_start(8080):
        print("  ✓ TCP Server 已启动")
        print("  >>> 手机连接 N657-WB3S, 密码 12345678")
        print("  >>> 网络调试助手连接 192.168.4.1:8080")
    else:
        print("  ✗ 启动失败")
        wb3s.close()
        return

    print("\n[3] 等待客户端数据... (按 USER 键退出)")
    led_on(LED_GREEN)

    try:
        while True:
            resp = wb3s.tcp_recv(timeout=1000)
            if resp:
                text = resp.decode("utf-8", errors="ignore")
                print(f"\n  收到: {text[:200]}")

                # 回复
                reply = f"WB3S Echo: {text[:50]}\n"
                wb3s.tcp_server_send(0, reply)
                print("  已回复")

            if BUTTON and BUTTON.value():
                print("\n[BTN] 退出")
                time.sleep_ms(200)
                break

            time.sleep_ms(100)

    except KeyboardInterrupt:
        pass

    wb3s.tcp_server_stop()
    led_off(LED_GREEN)
    wb3s.close()
    print("测试结束")


# =============================================================================
# 测试 6: 开机自动透传 (SAVETRANSLINK)
# =============================================================================


def save_auto_connect_test():
    """
    配置开机自动透传: 模块上电后自动连接 WiFi 并建立 TCP 透传。
    配置一次, 永久生效 (保存到 flash)。
    """
    print("=" * 50)
    print("  配置开机自动透传")
    print("=" * 50)

    wb3s = WB3S(
        uart_id=WB3S_UART_ID,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=RST_PIN,
        baudrate=WB3S_BAUD,
        debug=DEBUG,
    )

    if RST_PIN:
        wb3s.reset(2.0)
    wb3s.wait_ready(10)

    # 先连接 WiFi
    print("\n[1] 连接 WiFi (用于测试配置)...")
    if not wb3s.connect_wifi(WIFI_SSID, WIFI_PASSWORD, timeout=20000):
        print("  ✗ WiFi 连接失败")
        wb3s.close()
        return
    print("  ✓ WiFi 已连接")

    # 保存透传配置
    print(f"\n[2] 保存自动透传配置 -> {CLOUD_HOST}:{CLOUD_PORT}")
    print('  格式: AT+SAVETRANSLINK=1,"host",port,"TCP"')
    if wb3s.save_transparent_link(CLOUD_HOST, CLOUD_PORT, "TCP"):
        print("  ✓ 配置已保存!")
        print("  下次模块上电后将自动:")
        print(f"    1. 连接 WiFi: {WIFI_SSID}")
        print(f"    2. 连接服务器: {CLOUD_HOST}:{CLOUD_PORT}")
        print(f"    3. 进入透传模式")
    else:
        print("  ✗ 配置保存失败")

    print("\n  如需清除自动连接: AT+SAVETRANSLINK=0")
    wb3s.close()


# =============================================================================
# 入口 — 选择测试模式
# =============================================================================

if __name__ == "__main__":
    import sys

    print("""
+-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-+
|  WB3S AT 固件测试 — Nucleo-N657X0     |
|  芯片: BK7238  |  固件: AT 指令集      |
+-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-+
    """)

    # ------ 修改这里选择测试模式 ------
    TEST_MODE = 1
    # 1 = 快速连通性测试 (推荐先跑)
    # 2 = TCP Client 云端发送
    # 3 = 透传模式
    # 4 = 智能配网 (SmartConfig)
    # 5 = TCP Server 模式
    # 6 = 配置开机自动透传
    # --------------------------------

    test_names = {
        1: "快速连通性测试",
        2: "TCP Client 云端发送",
        3: "透传模式",
        4: "智能配网 (SmartConfig)",
        5: "TCP Server 模式",
        6: "配置开机自动透传",
    }
    test_funcs = {
        1: quick_test,
        2: tcp_client_test,
        3: transparent_mode_test,
        4: smart_config_test,
        5: tcp_server_test,
        6: save_auto_connect_test,
    }

    test = test_funcs.get(TEST_MODE, quick_test)
    print(f"执行: {test_names.get(TEST_MODE, '未知')}\n")
    test()

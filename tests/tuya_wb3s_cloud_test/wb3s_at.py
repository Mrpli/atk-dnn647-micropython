"""
WB3S AT 命令驱动 — 适用于 BK7238 AT 固件
==========================================

基于 XH-WB3S (BK7238 芯片) AT 固件 V3.0.7。
AT 指令集兼容 ESP8266 风格。

硬件接线 (Nucleo-N657X0 <-> WB3S):
    N657 D1 (PD8)  = UART3_TX  -->  WB3S RXD1 (pin 21)
    N657 D0 (PD9)  = UART3_RX  -->  WB3S TXD1 (pin 22)
    N657 D2 (PD0)  -->  WB3S CEN  (pin 1, 复位, 低电平有效)
    N657 3.3V      -->  WB3S VCC  (pin 8)
    N657 GND       -->  WB3S GND  (pin 15)

参考文档:
    - 拿到模块让我们开始吧 v2.0 (AT 指令使用指南)
    - SPARKLEIOT XH-WB3S 模组手册 V1.0 (硬件规格)
"""

import time
import struct
from machine import UART, Pin

# =============================================================================
# WB3S AT 驱动类
# =============================================================================


class WB3S:
    """
    WB3S AT 命令驱动 (BK7238 AT 固件)。

    使用示例 — 快速测试:
        wb3s = WB3S()
        wb3s.reset()
        print(wb3s.at_test())           # 测试 AT 通信

    使用示例 — 云端发数据 (TCP Client):
        wb3s = WB3S()
        wb3s.reset()
        wb3s.connect_wifi("ssid", "password")
        wb3s.tcp_connect("server.com", 8080)
        wb3s.tcp_send("Hello Cloud!")
        wb3s.tcp_close()

    使用示例 — 透传模式:
        wb3s = WB3S()
        wb3s.reset()
        wb3s.connect_wifi("ssid", "password")
        wb3s.transparent_connect("server.com", 8080)
        wb3s.send_raw(b"binary data here")  # 透传后直接发原始数据
        wb3s.exit_transparent()             # +++ 退出透传
    """

    # AT 响应状态
    OK = "OK"
    ERROR = "ERROR"
    READY = "ready"

    def __init__(
        self, uart_id=3, tx_pin="D1", rx_pin="D0", rst_pin="D2", baudrate=115200, debug=False
    ):
        """
        初始化 WB3S 驱动。

        参数:
            uart_id:  UART 端口 (UART3=3)
            tx_pin:   TX 引脚 (接 WB3S RXD1)
            rx_pin:   RX 引脚 (接 WB3S TXD1)
            rst_pin:  复位引脚 (接 WB3S CEN, 低电平复位)
            baudrate: 波特率 (默认 115200)
            debug:    是否打印调试信息
        """
        self._debug = debug
        self._baudrate = baudrate
        self._transparent_mode = False
        self._tcp_connected = False

        # 初始化 UART
        self._uart = UART(
            uart_id,
            baudrate=baudrate,
            bits=8,
            parity=None,
            stop=1,
            tx=Pin(tx_pin),
            rx=Pin(rx_pin),
            timeout=100,
            timeout_char=20,
            read_buf_len=1024,
        )

        # 复位引脚 (低电平有效)
        self._rst = Pin(rst_pin, Pin.OUT, value=1) if rst_pin else None

        if self._debug:
            print(f"[WB3S] UART{uart_id} @{baudrate}")

    # --------------------------------------------------------------------------
    # 底层通信
    # --------------------------------------------------------------------------

    def _log(self, msg):
        if self._debug:
            print(f"[WB3S] {msg}")

    def reset(self, delay=1.5):
        """
        硬件复位模块 (CEN 引脚拉低 ≥300ms)。
        复位后等待 ready 提示。
        """
        if self._rst is None:
            self._log("RST 引脚未配置, 跳过硬件复位")
            return False

        self._log("硬件复位...")
        self._uart.read()  # 清空缓冲区
        self._rst.low()
        time.sleep(0.35)  # ≥300ms
        self._rst.high()
        time.sleep(delay)  # 等待启动

        self._transparent_mode = False
        self._tcp_connected = False
        return True

    def send_at(self, cmd, timeout=3000, wait_for="OK\r\n"):
        """
        发送 AT 命令并等待响应。
        返回响应文本。

        参数:
            cmd:      AT 命令 (不含 \\r\\n)
            timeout:  超时毫秒
            wait_for: 等待的响应结束标记 (默认 'OK\\r\\n')

        返回: 响应文本 (已去除命令回显和结束标记)
        """
        if self._transparent_mode:
            self._log("警告: 当前处于透传模式, 请先退出透传")
            return ""

        full_cmd = cmd + "\r\n"
        self._log(f"TX: {cmd}")
        self._uart.write(full_cmd)

        start = time.ticks_ms()
        response = bytearray()

        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    response.extend(chunk)
                    text = response.decode("ascii", errors="ignore")

                    # 等待结束标记
                    if wait_for and wait_for in text:
                        break
                    # 透传模式响应 '>'
                    if wait_for == ">" and ">" in text:
                        break

            time.sleep_ms(5)

        text = response.decode("ascii", errors="ignore")

        # 清洗响应: 去掉命令回显和结束标记
        # AT 固件回显: 先回显命令, 然后 \\r\\n 响应 \\r\\n OK\\r\\n 或 ERROR\\r\\n
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 跳过命令回显
            if line == cmd.strip():
                continue
            clean_lines.append(line)

        clean_text = "\n".join(clean_lines)
        self._log(f"RX: {clean_text[:200]}")
        return clean_text

    def send_at_raw(self, data, timeout=500):
        """
        发送原始数据 (透传模式用)。
        返回原始响应 bytes。
        """
        self._uart.write(data)
        time.sleep_ms(timeout)
        response = b""
        if self._uart.any():
            response = self._uart.read(self._uart.any())
        return response

    def wait_ready(self, timeout=10):
        """
        等待模块启动就绪 (收到 "ready" 字符串)。
        返回 True 表示就绪。
        """
        self._log("等待模块就绪...")
        self._uart.read()
        start = time.time()
        buf = bytearray()
        while time.time() - start < timeout:
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    buf.extend(chunk)
                    text = buf.decode("ascii", errors="ignore").lower()
                    if "ready" in text:
                        self._log("模块就绪!")
                        return True
            time.sleep_ms(50)
        self._log("等待超时")
        return False

    # --------------------------------------------------------------------------
    # AT 测试
    # --------------------------------------------------------------------------

    def at_test(self):
        """
        AT 通信测试。
        发送 AT 命令, 返回是否收到 OK。
        """
        resp = self.send_at("AT", timeout=1000)
        return self.OK in resp

    def get_version(self):
        """查询固件版本"""
        return self.send_at("AT+GMR", timeout=1000)

    def get_chip_id(self):
        """查询芯片 ID (星火内部指令)"""
        return self.send_at("AT+CSYSID", timeout=1000)

    # --------------------------------------------------------------------------
    # WiFi 配置
    # --------------------------------------------------------------------------

    def set_mode(self, mode):
        """
        设置 WiFi 模式。
        mode: 1=STA, 2=AP, 3=STA+AP
        """
        return self.send_at(f"AT+CWMODE={mode}", timeout=1000)

    def scan_wifi(self, timeout=10000):
        """扫描附近 WiFi"""
        return self.send_at("AT+CWLAP", timeout=timeout, wait_for="OK\r\n")

    def connect_wifi(self, ssid, password, timeout=20000):
        """
        连接 WiFi (STA 模式)。
        返回 True 表示连接成功。
        """
        self._log(f"连接 WiFi: {ssid}")
        self.set_mode(1)
        time.sleep(0.5)

        cmd = f'AT+CWJAP="{ssid}","{password}"'
        resp = self.send_at(cmd, timeout=timeout)

        # 检查是否连接成功
        if self.OK in resp or "WIFI CONNECTED" in resp or "WIFI GOT IP" in resp:
            self._log("WiFi 连接成功")
            return True

        self._log(f"WiFi 连接失败: {resp}")
        return False

    def get_ip(self):
        """查询本机 IP 和 MAC"""
        return self.send_at("AT+CIFSR", timeout=1000)

    def set_ap(self, ssid, password, channel=11, encryption=0):
        """
        设置 AP 模式热点。
        encryption: 0=OPEN, 2=WPA_PSK, 3=WPA2_PSK, 4=WPA_WPA2_PSK
        """
        self.set_mode(2)
        time.sleep(0.3)
        cmd = f'AT+CWSAP="{ssid}","{password}",{channel},{encryption}'
        return self.send_at(cmd, timeout=1000)

    def smart_config(self, enable=True):
        """
        智能配网 (SmartConfig / BLUFI)。
        使用乐鑫 ESP-BLUFI App 配网。
        """
        cmd = f"AT+BLUFI={1 if enable else 0}"
        return self.send_at(cmd, timeout=3000)

    def restore(self):
        """恢复出厂设置"""
        return self.send_at("AT+RESTORE", timeout=5000)

    # --------------------------------------------------------------------------
    # 波特率设置
    # --------------------------------------------------------------------------

    def set_baudrate(self, baudrate):
        """
        修改串口波特率 (保存到 flash, 下次上电生效)。
        格式: AT+UART_DEF=baudrate,8,1,0,0
        """
        cmd = f"AT+UART_DEF={baudrate},8,1,0,0"
        resp = self.send_at(cmd, timeout=1000)
        if self.OK in resp:
            self._log(f"波特率已改为 {baudrate}, 重启后生效")
            return True
        return False

    # --------------------------------------------------------------------------
    # GPIO 操作
    # --------------------------------------------------------------------------

    def gpio_read(self, pin):
        """
        读取 IO 状态 (星火内部指令)。
        返回: 0=低电平, 1=高电平
        """
        resp = self.send_at(f"AT+CIOREAD={pin}", timeout=2000)
        # 返回值格式: +CIOREAD:0 或 +CIOREAD:1
        if "CIOREAD:0" in resp:
            return 0
        elif "CIOREAD:1" in resp:
            return 1
        return None

    def gpio_write(self, pin, value):
        """
        设置 IO 状态 (星火内部指令)。
        value: 0=低电平, 1=高电平
        """
        cmd = f"AT+CIOWRITE={pin},{1 if value else 0}"
        resp = self.send_at(cmd, timeout=2000)
        return self.OK in resp

    # --------------------------------------------------------------------------
    # TCP Client 模式
    # --------------------------------------------------------------------------

    def tcp_connect(self, host, port, timeout=15000):
        """
        连接 TCP 服务器 (非透传模式)。
        返回 True 表示连接成功。
        """
        self._log(f"TCP 连接: {host}:{port}")

        # 必须先设置单连接
        self.send_at("AT+CIPMUX=0", timeout=1000)
        time.sleep(0.2)
        # 关闭透传模式 (如果之前开启)
        self.send_at("AT+CIPMODE=0", timeout=1000)
        time.sleep(0.2)

        cmd = f'AT+CIPSTART="TCP","{host}",{port}'
        resp = self.send_at(cmd, timeout=timeout)

        if "CONNECT" in resp:
            self._log("TCP 连接成功")
            self._tcp_connected = True
            return True

        # ALREADY CONNECTED 也算成功
        if "ALREADY CONNECTED" in resp:
            self._log("TCP 已经连接")
            self._tcp_connected = True
            return True

        self._log(f"TCP 连接失败: {resp}")
        return False

    def tcp_send(self, data, timeout=5000):
        """
        在非透传模式下发送 TCP 数据。
        先发 AT+CIPSEND=<len>, 收到 > 提示后发数据。
        返回 True 表示发送成功。
        """
        if isinstance(data, str):
            data = data.encode("utf-8")

        cmd = f"AT+CIPSEND={len(data)}"
        resp = self.send_at(cmd, timeout=2000, wait_for=">")
        if ">" not in resp:
            self._log(f"未收到 '>' 提示: {resp}")
            return False

        # 发送实际数据 (不带 \\r\\n)
        self._log(f"发送 {len(data)} 字节")
        self._uart.write(data)

        # 等待发送结果
        start = time.ticks_ms()
        resp_buf = bytearray()
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    resp_buf.extend(chunk)
                    text = resp_buf.decode("ascii", errors="ignore")
                    if "SEND OK" in text:
                        self._log("发送成功")
                        return True
                    if self.ERROR in text:
                        self._log("发送失败")
                        return False
            time.sleep_ms(10)

        self._log("发送超时")
        return False

    def tcp_recv(self, timeout=500):
        """
        在非透传模式下接收 TCP 数据。
        返回收到的数据 (bytes), 没有数据返回 None。
        """
        buf = bytearray()
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    buf.extend(chunk)
            time.sleep_ms(10)

        if buf:
            text = buf.decode("ascii", errors="ignore")
            # 格式: +IPD,<len>:<data>
            if "+IPD," in text:
                # 提取数据部分
                idx = text.find("+IPD,")
                data_start = text.find(":", idx) + 1
                return buf[data_start:]
            return bytes(buf)
        return None

    def tcp_close(self):
        """关闭 TCP 连接"""
        self._transparent_mode = False
        self._tcp_connected = False
        resp = self.send_at("AT+CIPCLOSE", timeout=5000)
        return resp

    # --------------------------------------------------------------------------
    # TCP Server 模式
    # --------------------------------------------------------------------------

    def tcp_server_start(self, port=8080):
        """
        启动 TCP Server (必须在多连接模式下)。
        返回 True 表示成功。
        """
        self.send_at("AT+CIPMUX=1", timeout=1000)
        time.sleep(0.2)
        resp = self.send_at(f"AT+CIPSERVER=1,{port}", timeout=2000)
        return self.OK in resp

    def tcp_server_stop(self):
        """停止 TCP Server"""
        resp = self.send_at("AT+CIPSERVER=0", timeout=2000)
        return self.OK in resp

    def tcp_server_send(self, link_id, data):
        """
        Server 模式下向指定客户端发送数据。
        link_id: 客户端连接 ID (0-4)
        """
        if isinstance(data, str):
            data = data.encode("utf-8")
        cmd = f"AT+CIPSEND={link_id},{len(data)}"
        resp = self.send_at(cmd, timeout=2000, wait_for=">")
        if ">" in resp:
            self._uart.write(data)
            time.sleep_ms(300)
            return True
        return False

    # --------------------------------------------------------------------------
    # 透传模式
    # --------------------------------------------------------------------------

    def transparent_connect(self, host, port, timeout=15000):
        """
        进入 TCP 透传模式。
        建立 TCP 连接后自动进入透传, 可直接收发原始数据。

        退出透传: 发送 '+++' (不换行, 取消发送新行)
        """
        self._log(f"透传模式连接: {host}:{port}")
        self.send_at("AT+CIPMUX=0", timeout=1000)
        time.sleep(0.2)
        self.send_at("AT+CIPMODE=1", timeout=1000)  # 开透传
        time.sleep(0.2)

        cmd = f'AT+CIPSTART="TCP","{host}",{port}'
        resp = self.send_at(cmd, timeout=timeout, wait_for="CONNECT")

        if "CONNECT" in resp:
            self._transparent_mode = True
            self._tcp_connected = True

            # 连接成功后, 马上发 AT+CIPSEND 进入透传发送模式
            self.send_at("AT+CIPSEND", timeout=2000, wait_for=">")

            self._log("进入透传模式")
            return True

        self._log(f"透传连接失败: {resp}")
        return False

    def send_raw(self, data):
        """
        透传模式下发送原始数据 (无需 AT 命令包裹)。
        数据会直接发送到远端。
        """
        if not self._transparent_mode:
            self._log("警告: 不在透传模式")
            return False

        if isinstance(data, str):
            data = data.encode("utf-8")

        self._log(f"透传送 {len(data)} 字节")
        self._uart.write(data)
        return True

    def recv_raw(self, timeout=200):
        """
        透传模式下接收原始数据。
        """
        if self._uart.any():
            return self._uart.read(self._uart.any())
        return None

    def exit_transparent(self):
        """
        退出透传模式。
        发送 '+++' (不带换行)。
        """
        if not self._transparent_mode:
            return True

        self._log("退出透传模式...")
        # +++ 必须在无数据发送至少 1 秒后发送
        time.sleep(1.0)
        self._uart.write("+++")
        time.sleep(0.5)

        # 读取响应
        resp = ""
        if self._uart.any():
            resp = self._uart.read(self._uart.any()).decode("ascii", errors="ignore")

        self._transparent_mode = False
        self._log(f"透传已退出: {resp}")
        return self.OK in resp or "OK" in resp

    # --------------------------------------------------------------------------
    # 开机自动透传 (SAVETRANSLINK)
    # --------------------------------------------------------------------------

    def save_transparent_link(self, host, port, protocol="TCP"):
        """
        保存透传连接参数到 flash。
        下次开机自动进入透传模式连接指定服务器。

        格式: AT+SAVETRANSLINK=1,"host",port,"TCP"
        """
        cmd = f'AT+SAVETRANSLINK=1,"{host}",{port},"{protocol}"'
        resp = self.send_at(cmd, timeout=3000)
        return self.OK in resp

    def clear_saved_link(self):
        """清除已保存的透传连接参数"""
        resp = self.send_at("AT+SAVETRANSLINK=0", timeout=2000)
        return self.OK in resp

    # --------------------------------------------------------------------------
    # MAC 地址
    # --------------------------------------------------------------------------

    def set_mac(self, mac):
        """
        设置 STA 模式 MAC 地址。
        mac: "18:fe:35:98:d3:7b"
        """
        cmd = f'AT+CIPSTAMAC="{mac}"'
        resp = self.send_at(cmd, timeout=1000)
        return self.OK in resp

    # --------------------------------------------------------------------------
    # 便捷: 通过 TCP 发送 HTTP POST (向云端上报数据)
    # --------------------------------------------------------------------------

    def http_post(self, host, port, path, body, timeout=15000):
        """
        通过 TCP 发送 HTTP POST 请求并返回响应。
        常用于向 REST API 云端上报数据。

        参数:
            host: 服务器地址
            port: 端口 (通常是 80 或 443)
            path: 请求路径 (如 "/api/data")
            body: 请求体 (JSON 字符串)
            timeout: 超时毫秒

        返回: HTTP 响应体文本

        示例:
            data = '{"temperature":25.5,"humidity":60.0}'
            resp = wb3s.http_post("myserver.com", 8080, "/api/sensor", data)
        """
        if not self.tcp_connect(host, port, timeout=timeout):
            return None

        # 构造 HTTP POST 请求
        if isinstance(body, str):
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = body

        http_req = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8") + body_bytes

        if self._transparent_mode:
            self.send_raw(http_req)
        else:
            self.tcp_send(http_req)

        # 接收响应
        time.sleep(0.5)
        resp = b""
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    resp += chunk
            time.sleep_ms(20)
            if resp and (b"\r\n\r\n" in resp or b"\n\n" in resp):
                # 继续读 body
                time.sleep_ms(200)
                if self._uart.any():
                    resp += self._uart.read(self._uart.any())
                break

        self.tcp_close()
        return resp.decode("utf-8", errors="ignore")

    # --------------------------------------------------------------------------
    # 资源释放
    # --------------------------------------------------------------------------

    def close(self):
        """关闭 UART 连接"""
        if self._tcp_connected:
            if self._transparent_mode:
                self.exit_transparent()
            self.tcp_close()
        self._uart.deinit()

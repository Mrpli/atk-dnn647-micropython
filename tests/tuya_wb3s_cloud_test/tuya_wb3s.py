"""
Tuya WB3S MCU Protocol Driver for MicroPython
=============================================

用于 Nucleo-N657X0 通过 UART3 与 WB3S WiFi+BLE 模块通信，
实现 Tuya 串行协议，支持向 Tuya Cloud 发送数据。

硬件接线 (Nucleo-N657X0 <-> WB3S):
    N657 D1 (PD8)  = UART3_TX  -->  WB3S RX
    N657 D0 (PD9)  = UART3_RX  -->  WB3S TX
    N657 3.3V      -->  WB3S VCC
    N657 GND       -->  WB3S GND
    N657 D2 (PD0)  -->  WB3S RST (可选，用于硬件复位)
    N657 D3 (PE9)  -->  WB3S GPIO0 (可选，用于进入配网模式)

协议参考: Tuya MCU SDK 串行通信协议 V3.3
帧格式: [55 AA] [Version] [Command] [Len_H] [Len_L] [Data...] [Checksum]
"""

import time
import struct
from machine import UART, Pin

# =============================================================================
# 协议常量
# =============================================================================

# 帧头
FRAME_HEADER = b"\x55\xaa"

# 命令字 (MCU -> WB3S 模块)
CMD_HEARTBEAT = 0x00  # 心跳包
CMD_PRODUCT_INFO = 0x01  # 产品信息
CMD_QUERY_WORK_MODE = 0x02  # 查询工作模式
CMD_REPORT_NETWORK = 0x03  # 上报网络状态
CMD_RESET_WIFI = 0x04  # 重置 WiFi
CMD_RESET_WIFI_MODE = 0x05  # 重置 WiFi 并选择模式
CMD_SEND_DP = 0x06  # 发送 DP 数据点到云端
CMD_QUERY_STATUS = 0x07  # 查询状态
CMD_START_FW_UPDATE = 0x08  # 启动固件升级
CMD_GET_FW_VERSION = 0x0A  # 获取 MCU 固件版本
CMD_WIFI_READY = 0x0B  # 通知 MCU WiFi 就绪
CMD_GET_SIGNAL = 0x0C  # 获取 WiFi 信号强度
CMD_GET_LOCAL_TIME = 0x1C  # 获取本地时间

# 命令字 (WB3S -> MCU)
# 大部分与上述相同，由模块主动下发

# DP (Data Point) 数据类型
DP_TYPE_RAW = 0x00  # 原始数据
DP_TYPE_BOOL = 0x01  # 布尔型
DP_TYPE_VALUE = 0x02  # 数值型 (4字节大端)
DP_TYPE_STRING = 0x03  # 字符串型
DP_TYPE_ENUM = 0x04  # 枚举型
DP_TYPE_FAULT = 0x05  # 故障型

# 网络状态
NETWORK_STATUS = {
    0x00: "已连接",
    0x01: "已连接但未配网",
    0x02: "正在连接",
    0x03: "未连接",
    0x04: "连接超时",
    0x05: "连接失败",
}

# WiFi 工作模式
WIFI_MODE_LOW_POWER = 0x00  # 低功耗模式
WIFI_MODE_NORMAL = 0x01  # 普通模式
WIFI_MODE_CONFIG = 0x02  # 配网模式 (EZ Mode)


# =============================================================================
# 异常定义
# =============================================================================


class TuyaError(Exception):
    """Tuya 协议通用异常"""

    pass


class TuyaChecksumError(TuyaError):
    """校验和错误"""

    pass


class TuyaTimeoutError(TuyaError):
    """通信超时"""

    pass


class TuyaInvalidResponse(TuyaError):
    """无效的响应"""

    pass


# =============================================================================
# WB3S 驱动类
# =============================================================================


class WB3S:
    """
    WB3S 模块驱动，实现 Tuya MCU 串行通信协议。

    使用示例:
        wb3s = WB3S(uart_id=3, tx_pin='D1', rx_pin='D0', rst_pin='D2')
        wb3s.init()

        # 等待模块就绪
        if wb3s.wait_ready(timeout=10):
            print("WB3S 就绪")

        # 进入配网模式
        wb3s.start_config_mode()

        # 等待 WiFi 连接
        if wb3s.wait_wifi_connected(timeout=60):
            print("WiFi 已连接")

        # 发送数据到云端
        wb3s.send_dp(1, DP_TYPE_VALUE, 2500)     # DP1: 数值
        wb3s.send_dp(2, DP_TYPE_BOOL, True)       # DP2: 开关状态
        wb3s.send_dp(3, DP_TYPE_STRING, "Hello")  # DP3: 字符串
    """

    def __init__(
        self,
        uart_id=3,
        tx_pin="D1",
        rx_pin="D0",
        rst_pin=None,
        cfg_pin=None,
        baudrate=115200,
        product_id="",
        mcu_version="1.0.0",
        debug=False,
    ):
        """
        初始化 WB3S 驱动。

        参数:
            uart_id: UART 端口号 (N657 上 UART3=3)
            tx_pin:  TX 引脚名称
            rx_pin:  RX 引脚名称
            rst_pin: 复位引脚 (可选)
            cfg_pin: 配网模式引脚 (可选, 拉低进入 EZ 配网)
            baudrate: 波特率, WB3S 默认 115200
            product_id: 产品 ID (对应 Tuya IoT 平台的产品 PID)
            mcu_version: MCU 固件版本号字符串
            debug: 是否打印调试信息
        """
        self._debug = debug
        self._product_id = product_id
        self._mcu_version = mcu_version
        self._recv_buf = bytearray()
        self._network_status = 0x03  # 初始: 未连接
        self._wifi_ready = False

        # 初始化 UART
        self._uart = UART(
            uart_id,
            baudrate=baudrate,
            bits=8,
            parity=None,
            stop=1,
            tx=Pin(tx_pin),
            rx=Pin(rx_pin),
            timeout=50,
            timeout_char=10,
            read_buf_len=512,
        )

        # 初始化可选引脚
        self._rst_pin = Pin(rst_pin, Pin.OUT, value=1) if rst_pin else None
        self._cfg_pin = Pin(cfg_pin, Pin.OUT, value=1) if cfg_pin else None

        if self._debug:
            print(f"[WB3S] 初始化完成, UART{uart_id}, baud={baudrate}")

    # --------------------------------------------------------------------------
    # 硬件控制
    # --------------------------------------------------------------------------

    def reset(self, delay=1.0):
        """
        硬件复位 WB3S 模块。
        需要连接 RST 引脚。
        """
        if self._rst_pin is None:
            if self._debug:
                print("[WB3S] RST 引脚未配置, 跳过硬件复位")
            return

        if self._debug:
            print("[WB3S] 硬件复位模块...")
        self._rst_pin.low()
        time.sleep(0.1)
        self._rst_pin.high()
        time.sleep(delay)
        self._recv_buf = bytearray()
        self._wifi_ready = False

    def set_config_mode(self, enter=True):
        """
        设置配网模式引脚。
        拉低进入 EZ Mode 配网, 拉高退出。
        """
        if self._cfg_pin is None:
            if self._debug:
                print("[WB3S] CFG 引脚未配置")
            return
        self._cfg_pin.value(0 if enter else 1)
        if self._debug:
            print(f"[WB3S] 配网模式: {'进入' if enter else '退出'}")

    # --------------------------------------------------------------------------
    # 协议底层
    # --------------------------------------------------------------------------

    @staticmethod
    def _checksum(data):
        """计算校验和: 所有字节之和的低 8 位"""
        return sum(data) & 0xFF

    def _build_frame(self, cmd, data=b""):
        """
        构建 Tuya 协议帧。

        帧格式:
            [55 AA] [Version(1)] [Cmd(1)] [Len_H(1)] [Len_L(1)] [Data(N)] [Checksum(1)]
        """
        version = 0x00
        data_len = len(data)
        header_and_data = bytes([version, cmd, (data_len >> 8) & 0xFF, data_len & 0xFF]) + data
        cksum = self._checksum(header_and_data)
        frame = FRAME_HEADER + header_and_data + bytes([cksum])
        return frame

    def _parse_frame(self, frame):
        """
        解析 Tuya 协议帧, 返回 (cmd, data) 或 None。
        """
        if len(frame) < 7:
            return None

        if frame[0:2] != FRAME_HEADER:
            return None

        version = frame[2]
        cmd = frame[3]
        data_len = (frame[4] << 8) | frame[5]

        if len(frame) < 7 + data_len:
            return None

        data = frame[6 : 6 + data_len]
        expected_cksum = self._checksum(frame[2 : 6 + data_len])
        actual_cksum = frame[6 + data_len]

        if expected_cksum != actual_cksum:
            if self._debug:
                print(f"[WB3S] 校验错误: calc={expected_cksum:02X}, recv={actual_cksum:02X}")
            return None

        return (cmd, data)

    def _send_cmd(self, cmd, data=b""):
        """发送命令帧"""
        frame = self._build_frame(cmd, data)
        if self._debug:
            hex_str = " ".join(f"{b:02X}" for b in frame)
            print(f"[WB3S] TX: {hex_str}")
        self._uart.write(frame)

    def _read_frame(self, timeout=1000):
        """
        从 UART 读取一个完整的 Tuya 帧。
        返回 (cmd, data) 或超时返回 None。
        """
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            # 读取所有可用数据
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    self._recv_buf.extend(chunk)
                    if self._debug:
                        hex_str = " ".join(f"{b:02X}" for b in chunk)
                        print(f"[WB3S] RX raw: {hex_str}")

            # 尝试解析帧
            while len(self._recv_buf) >= 7:
                # 查找帧头
                idx = self._recv_buf.find(FRAME_HEADER)
                if idx < 0:
                    self._recv_buf = bytearray()
                    break
                if idx > 0:
                    # 丢弃帧头之前的无效字节
                    self._recv_buf = self._recv_buf[idx:]

                # 读取数据长度
                if len(self._recv_buf) < 6:
                    break
                data_len = (self._recv_buf[4] << 8) | self._recv_buf[5]
                frame_len = 7 + data_len

                if len(self._recv_buf) < frame_len:
                    break  # 等待更多数据

                frame = bytes(self._recv_buf[:frame_len])
                self._recv_buf = self._recv_buf[frame_len:]

                result = self._parse_frame(frame)
                if result:
                    cmd, data = result
                    if self._debug:
                        print(
                            f"[WB3S] RX: cmd={cmd:02X}, data={' '.join(f'{b:02X}' for b in data) if data else '(empty)'}"
                        )
                    return result

            time.sleep_ms(10)

        return None

    def _cmd_exchange(self, cmd, data=b"", timeout=2000):
        """
        发送命令并等待响应。
        返回 (resp_cmd, resp_data) 或超时抛出异常。
        """
        self._send_cmd(cmd, data)
        result = self._read_frame(timeout)
        if result is None:
            raise TuyaTimeoutError(f"命令 0x{cmd:02X} 无响应")
        return result

    # --------------------------------------------------------------------------
    # 协议处理
    # --------------------------------------------------------------------------

    def _process_heartbeat(self):
        """处理心跳包: 收到模块心跳, 回应"""
        self._send_cmd(CMD_HEARTBEAT)

    def _process_product_info_query(self):
        """处理产品信息查询: 回应产品 ID 和 MCU 版本"""
        # 格式: {"p":"产品ID","v":"MCU版本号"}
        info = '{{"p":"{}","v":"{}"}}'.format(self._product_id, self._mcu_version)
        self._send_cmd(CMD_PRODUCT_INFO, info.encode("ascii"))

    def _process_network_status(self, data):
        """处理网络状态上报"""
        if data and len(data) >= 1:
            self._network_status = data[0]
            status_text = NETWORK_STATUS.get(
                self._network_status, f"未知({self._network_status:02X})"
            )
            if self._debug:
                print(f"[WB3S] 网络状态: {status_text}")
            if self._network_status == 0x00:
                self._wifi_ready = True

    def _process_cmd(self, cmd, data):
        """
        处理来自 WB3S 的命令。
        返回 True 表示需要继续轮询, False 表示不需要。
        """
        if cmd == CMD_HEARTBEAT:
            self._process_heartbeat()
        elif cmd == CMD_PRODUCT_INFO:
            self._process_product_info_query()
        elif cmd == CMD_REPORT_NETWORK:
            self._process_network_status(data)
        elif cmd == CMD_RESET_WIFI:
            if self._debug:
                print("[WB3S] WiFi 重置响应")
        elif cmd == CMD_WIFI_READY:
            self._wifi_ready = True
            if self._debug:
                print("[WB3S] 模块上报 WiFi 就绪")
        elif cmd == CMD_SEND_DP:
            if self._debug and data:
                print(f"[WB3S] 收到云端下发的 DP 数据: {' '.join(f'{b:02X}' for b in data)}")
        else:
            if self._debug:
                print(f"[WB3S] 未处理命令: 0x{cmd:02X}")

    def poll(self, timeout=50):
        """
        轮询处理来自 WB3S 的数据。
        应该在主循环中定期调用。
        """
        result = self._read_frame(timeout=timeout)
        if result:
            cmd, data = result
            self._process_cmd(cmd, data)
            return True
        return False

    # --------------------------------------------------------------------------
    # 初始化与状态
    # --------------------------------------------------------------------------

    def init(self):
        """
        初始化 WB3S 通信。
        清空缓冲区, 等待模块启动。
        """
        # 清空接收缓冲
        self._uart.read()
        self._recv_buf = bytearray()
        if self._debug:
            print("[WB3S] 通信初始化完成")

    def wait_ready(self, timeout=10):
        """
        等待 WB3S 模块就绪 (收到心跳或产品信息查询)。
        返回 True 表示就绪。
        """
        if self._debug:
            print("[WB3S] 等待模块就绪...")
        start = time.time()
        while time.time() - start < timeout:
            result = self._read_frame(timeout=1000)
            if result:
                cmd, data = result
                if cmd in (CMD_HEARTBEAT, CMD_PRODUCT_INFO):
                    self._process_cmd(cmd, data)
                    if self._debug:
                        print("[WB3S] 模块就绪!")
                    return True
            self.poll(timeout=100)
        return False

    def is_wifi_ready(self):
        """检查 WiFi 是否已连接云端"""
        return self._wifi_ready and self._network_status == 0x00

    def wait_wifi_connected(self, timeout=60):
        """
        等待 WiFi 连接成功。
        返回 True 表示已连接。
        """
        if self._debug:
            print("[WB3S] 等待 WiFi 连接...")
        start = time.time()
        while time.time() - start < timeout:
            self.poll(timeout=500)
            if self.is_wifi_ready():
                if self._debug:
                    print("[WB3S] WiFi 已连接!")
                return True
            time.sleep_ms(200)
        return False

    def get_network_status(self):
        """获取当前网络状态码"""
        return self._network_status

    def get_network_status_text(self):
        """获取当前网络状态文本"""
        return NETWORK_STATUS.get(self._network_status, f"未知状态(0x{self._network_status:02X})")

    # --------------------------------------------------------------------------
    # WiFi 控制
    # --------------------------------------------------------------------------

    def start_config_mode(self, mode=WIFI_MODE_CONFIG):
        """
        进入配网模式。
        模块将进入 EZ Mode (SmartConfig), 可通过 Tuya Smart Life App 配网。

        mode: WIFI_MODE_LOW_POWER / WIFI_MODE_NORMAL / WIFI_MODE_CONFIG
        """
        if self._debug:
            print(f"[WB3S] 进入配网模式 (mode={mode})...")
        self._send_cmd(CMD_RESET_WIFI_MODE, bytes([mode]))

    def reset_wifi(self):
        """重置 WiFi 设置 (清除已保存的 WiFi 凭据)"""
        if self._debug:
            print("[WB3S] 重置 WiFi...")
        self._send_cmd(CMD_RESET_WIFI)
        self._wifi_ready = False

    def query_status(self):
        """查询模块状态"""
        return self._cmd_exchange(CMD_QUERY_STATUS, timeout=2000)

    def get_wifi_signal(self):
        """
        获取 WiFi 信号强度。
        返回信号强度值 (dBm 绝对值) 或 None。
        """
        try:
            resp_cmd, data = self._cmd_exchange(CMD_GET_SIGNAL, timeout=2000)
            if resp_cmd == CMD_GET_SIGNAL and len(data) >= 1:
                # 返回值是信号强度的绝对值 (如 40 表示 -40dBm)
                return data[0]
        except TuyaError:
            pass
        return None

    # --------------------------------------------------------------------------
    # 数据发送 (到云端)
    # --------------------------------------------------------------------------

    def send_dp(self, dp_id, dp_type, value):
        """
        发送一个 DP (Data Point) 数据点到云端。

        参数:
            dp_id:   DP ID 编号 (对应 Tuya IoT 平台定义的功能点)
            dp_type: DP 数据类型 (DP_TYPE_BOOL, DP_TYPE_VALUE, DP_TYPE_STRING, DP_TYPE_ENUM)
            value:   要发送的值

        示例:
            wb3s.send_dp(1, DP_TYPE_BOOL, True)       # 开关值
            wb3s.send_dp(2, DP_TYPE_VALUE, 2500)       # 数值 (4字节)
            wb3s.send_dp(3, DP_TYPE_STRING, "Hello")   # 字符串
            wb3s.send_dp(4, DP_TYPE_ENUM, 1)           # 枚举值
        """
        # 构造 DP 数据
        dp_data = bytes([dp_id, dp_type])

        if dp_type == DP_TYPE_BOOL:
            # 布尔型: 1 字节 (0x00 / 0x01)
            dp_data += bytes([1, 0x01 if value else 0x00])
        elif dp_type == DP_TYPE_VALUE:
            # 数值型: 4 字节大端整数
            dp_data += bytes([4])
            dp_data += struct.pack(">I", int(value))
        elif dp_type == DP_TYPE_STRING:
            # 字符串型
            value_bytes = str(value).encode("utf-8")
            dp_data += bytes([len(value_bytes)])
            dp_data += value_bytes
        elif dp_type == DP_TYPE_ENUM:
            # 枚举型: 1 字节
            dp_data += bytes([1, int(value)])
        elif dp_type == DP_TYPE_RAW:
            # 原始数据
            if isinstance(value, (bytes, bytearray)):
                dp_data += bytes([len(value)])
                dp_data += bytes(value)
            else:
                value_bytes = bytes(value)
                dp_data += bytes([len(value_bytes)])
                dp_data += value_bytes
        else:
            raise TuyaError(f"不支持的 DP 类型: 0x{dp_type:02X}")

        if self._debug:
            hex_str = " ".join(f"{b:02X}" for b in dp_data)
            print(f"[WB3S] 发送 DP: DP{int(dp_id)} type={dp_type}, data={hex_str}")

        try:
            resp_cmd, resp_data = self._cmd_exchange(CMD_SEND_DP, dp_data, timeout=3000)
            if resp_cmd == CMD_SEND_DP:
                if self._debug:
                    print("[WB3S] DP 发送成功")
                return True
        except TuyaError as e:
            if self._debug:
                print(f"[WB3S] DP 发送失败: {e}")
        return False

    def send_multi_dp(self, dp_list):
        """
        批量发送多个 DP 数据点。

        参数:
            dp_list: DP 列表，每项为 (dp_id, dp_type, value)

        示例:
            wb3s.send_multi_dp([
                (1, DP_TYPE_BOOL, True),
                (2, DP_TYPE_VALUE, 2500),
                (3, DP_TYPE_STRING, "Hello"),
            ])
        """
        dp_data = bytearray()
        for dp_id, dp_type, value in dp_list:
            dp_data.append(dp_id)
            dp_data.append(dp_type)

            if dp_type == DP_TYPE_BOOL:
                dp_data.extend([1, 0x01 if value else 0x00])
            elif dp_type == DP_TYPE_VALUE:
                dp_data.append(4)
                dp_data.extend(struct.pack(">I", int(value)))
            elif dp_type == DP_TYPE_STRING:
                value_bytes = str(value).encode("utf-8")
                dp_data.append(len(value_bytes))
                dp_data.extend(value_bytes)
            elif dp_type == DP_TYPE_ENUM:
                dp_data.extend([1, int(value)])
            elif dp_type == DP_TYPE_RAW:
                if isinstance(value, (bytes, bytearray)):
                    dp_data.append(len(value))
                    dp_data.extend(value)
                else:
                    value_bytes = bytes(value)
                    dp_data.append(len(value_bytes))
                    dp_data.extend(value_bytes)

        if self._debug:
            hex_str = " ".join(f"{b:02X}" for b in dp_data)
            print(f"[WB3S] 批量发送 DP: {hex_str}")

        try:
            resp_cmd, resp_data = self._cmd_exchange(CMD_SEND_DP, bytes(dp_data), timeout=3000)
            if resp_cmd == CMD_SEND_DP:
                if self._debug:
                    print("[WB3S] 批量 DP 发送成功")
                return True
        except TuyaError as e:
            if self._debug:
                print(f"[WB3S] 批量 DP 发送失败: {e}")
        return False

    # --------------------------------------------------------------------------
    # 便捷方法
    # --------------------------------------------------------------------------

    def get_local_time(self):
        """
        从云端获取本地时间。
        返回 (year, month, day, hour, minute, second) 元组。
        """
        try:
            resp_cmd, data = self._cmd_exchange(CMD_GET_LOCAL_TIME, timeout=3000)
            if resp_cmd == CMD_GET_LOCAL_TIME and len(data) >= 7:
                # 格式: year(1) month(1) day(1) hour(1) min(1) sec(1) [week_day(1)]
                return tuple(data[0:6])
        except TuyaError:
            pass
        return None

    def report_mcu_version(self):
        """上报 MCU 固件版本号"""
        version_bytes = self._mcu_version.encode("ascii")
        self._send_cmd(CMD_GET_FW_VERSION, version_bytes)

    def close(self):
        """关闭 UART 连接"""
        self._uart.deinit()


# =============================================================================
# 便捷: AT 命令模式 (适用于 WB3S 刷 AT 固件的情况)
# =============================================================================


class WB3S_AT:
    """
    WB3S AT 命令模式驱动。
    适用于刷入了 AT 固件的 WB3S 模块。
    """

    def __init__(
        self, uart_id=3, tx_pin="D1", rx_pin="D0", rst_pin=None, baudrate=115200, debug=False
    ):
        self._debug = debug
        self._uart = UART(
            uart_id,
            baudrate=baudrate,
            bits=8,
            parity=None,
            stop=1,
            tx=Pin(tx_pin),
            rx=Pin(rx_pin),
            timeout=100,
            timeout_char=10,
            read_buf_len=512,
        )
        self._rst_pin = Pin(rst_pin, Pin.OUT, value=1) if rst_pin else None
        self._recv_buf = bytearray()

    def reset(self, delay=1.0):
        """硬件复位"""
        if self._rst_pin:
            self._rst_pin.low()
            time.sleep(0.1)
            self._rst_pin.high()
            time.sleep(delay)
            self._uart.read()

    def send_at(self, cmd, timeout=3000):
        """发送 AT 命令并等待响应"""
        full_cmd = cmd + "\r\n"
        self._uart.write(full_cmd)
        if self._debug:
            print(f"[AT] TX: {cmd}")

        start = time.ticks_ms()
        response = bytearray()
        while time.ticks_diff(time.ticks_ms(), start) < timeout:
            if self._uart.any():
                chunk = self._uart.read(self._uart.any())
                if chunk:
                    response.extend(chunk)
                    if response.endswith(b"OK\r\n") or response.endswith(b"ERROR\r\n"):
                        break
            time.sleep_ms(10)

        text = response.decode("ascii", errors="ignore").strip()
        if self._debug:
            print(f"[AT] RX: {text}")
        return text

    def test(self):
        """AT 通信测试"""
        resp = self.send_at("AT")
        return "OK" in resp

    def connect_wifi(self, ssid, password, timeout=30):
        """
        连接 WiFi。
        AT+CWJAP="SSID","PASSWORD"
        """
        cmd = f'AT+CWJAP="{ssid}","{password}"'
        resp = self.send_at(cmd, timeout=timeout * 1000)
        return "OK" in resp or "WIFI CONNECTED" in resp

    def connect_tcp(self, host, port):
        """建立 TCP 连接"""
        cmd = f'AT+CIPSTART="TCP","{host}",{port}'
        resp = self.send_at(cmd, timeout=10000)
        return "OK" in resp or "CONNECT" in resp

    def send_tcp(self, data):
        """通过 TCP 发送数据"""
        if isinstance(data, str):
            data = data.encode("utf-8")
        cmd = f"AT+CIPSEND={len(data)}"
        resp = self.send_at(cmd, timeout=5000)
        if ">" in resp:
            self._uart.write(data)
            time.sleep(0.5)
            resp2 = self.send_at("", timeout=3000)
            return "SEND OK" in resp2
        return False

    def get_ip(self):
        """查询本机 IP"""
        resp = self.send_at("AT+CIFSR")
        return resp

    def close(self):
        """关闭连接"""
        self._uart.deinit()

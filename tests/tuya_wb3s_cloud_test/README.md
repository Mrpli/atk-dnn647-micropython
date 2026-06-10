# WB3S AT 固件云端测试 — Nucleo-N657X0

## 概述

使用 Nucleo-N657X0 通过 UART3 控制 **XH-WB3S** (BK7238 芯片, AT 固件) WiFi+BLE 模块，
通过 TCP 向云端服务器发送传感器数据。

- **芯片**: BK7238 (32-bit MCU, 160MHz, 256KB RAM, 2MB Flash)
- **固件**: AT 指令集 (兼容 ESP8266 风格)
- **通信**: UART, 115200 bps, 8N1
- **协议**: 标准 AT 命令

## 文件说明

| 文件 | 说明 |
|------|------|
| [wb3s_at.py](wb3s_at.py) | WB3S AT 驱动库 (完整版) |
| [main.py](main.py) | 测试主程序 (6 种测试模式) |
| [tuya_wb3s_standalone.py](tuya_wb3s_standalone.py) | 单文件精简版 (含驱动+测试) |

旧文件 (涂鸦协议, 不适配本模块):
- `tuya_wb3s.py` — Tuya MCU 协议驱动 (适用于涂鸦 SDK 固件, **此处不用**)

## 硬件接线

### WB3S 模块引脚 (XH-WB3S)

```
        WB3S 模块 (顶视图, 天线朝上)
     ___________________________
    |  o  o  o  o  o  o  o  o   |
    |                           |
    |         XH-WB3S           |
    |                           |
    |  o  o  o  o  o  o  o  o   |
     ---------------------------
       |  |  |  |  |  |  |  |
       |  |  |  |  |  |  |  +-- pin 16: P9
       |  |  |  |  |  |  +----- pin 15: GND
       |  |  |  |  |  +-------- pin 14: P17
       ... (具体以实物丝印为准)

关键引脚 (参考 SPARKLEIOT 模组手册 V1.0):

| Pin | 名称 | 类型 | 功能 |
|-----|------|------|------|
| 1   | CEN  | I/O  | 复位 (低电平有效), 内部上拉 |
| 8   | VCC  | P    | 3.3V 供电 |
| 15  | GND  | P    | 地 |
| 21  | RXD1 | I/O  | UART1 RX (接 MCU TX) |
| 22  | TXD1 | I/O  | UART1 TX (接 MCU RX) |
```

### 连接表

| Nucleo-N657X0 | Arduino 丝印 | 信号 | WB3S 引脚 |
|---------------|-------------|------|-----------|
| PD8           | D1          | UART3 TX | RXD1 (pin 21) |
| PD9           | D0          | UART3 RX | TXD1 (pin 22) |
| PD0           | D2          | GPIO | CEN (pin 1, 复位) |
| 3.3V          | 3.3V        | VCC | VCC (pin 8) |
| GND           | GND         | GND | GND (pin 15) |

> ⚠️ **供电要求**: 3.3V / ≥500mA, 峰值电流可 >400mA

### 接线示意图

```
   Nucleo-N657X0                   XH-WB3S
   =============                   ========

   CN8:
   [D1] PD8  ------------------->  RXD1 (pin 21)  UART3_TX
   [D0] PD9  <-------------------  TXD1 (pin 22)  UART3_RX
   [D2] PD0  ------------------->  CEN  (pin 1)   复位 (低有效)

   CN5:
   3.3V      ------------------->  VCC  (pin 8)
   GND       ------------------->  GND  (pin 15)
```

## 部署运行

```bash
# 快速测试版 (单个文件)
mpremote cp tuya_wb3s_standalone.py :main.py
mpremote reset

# 完整版 (两个文件)
mpremote cp wb3s_at.py :wb3s_at.py
mpremote cp main.py :main.py
mpremote reset
```

## 测试模式

修改 `main.py` 中的 `TEST_MODE`:

| 模式 | 功能 | 说明 |
|------|------|------|
| **1** | 快速连通性测试 | 验证 AT 通信 / 固件版本 / WiFi 扫描 (推荐先跑) |
| **2** | TCP Client 上报 | 连 WiFi → 连云端 TCP → 周期发送 JSON 数据 |
| **3** | 透传模式 | TCP 透传, 低延迟持续收发 |
| **4** | 智能配网 | 手机 ESP-BLUFI App 配网 (首次使用) |
| **5** | TCP Server | 模块做 AP+服务器, 手机连接 |
| **6** | 开机自动透传 | 保存配置到 Flash, 上电自动联网 |

## 使用步骤

### 1. 先跑快速连通性测试

`TEST_MODE = 1`

确认串口输出:
```
✓ 快速测试通过! 硬件连接正常.
```

### 2. 修改 WiFi 配置

在 `main.py` 中修改:
```python
WIFI_SSID     = "你的WiFi名称"    # 必须 2.4GHz!
WIFI_PASSWORD = "你的WiFi密码"
```

### 3. 运行模式 4 配网 (首次) 或直接模式 2

```python
TEST_MODE = 4  # 智能配网
# 或
TEST_MODE = 2  # 直接连接 WiFi 并上报
```

### 4. 数据上报

模式 2 会每 10 秒向云端 TCP 服务器发送一条 JSON:

```json
{"dev":"N657-WB3S","id":1,"temp":25.2,"hum":60.5}
```

## 云端接收端搭建

### 方法 1: 简易 TCP 服务器 (测试用)

在服务器上运行:
```bash
# Linux/Mac
nc -l 6602

# Python
python3 -c "
import socketserver
class H(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            data = self.rfile.readline()
            if not data: break
            print(data.decode().strip())
socketserver.TCPServer(('0.0.0.0', 6602), H).serve_forever()
"
```

### 方法 2: 使用在线 TCP 测试服务

http://tcp.doit.am/ — 创建免费 TCP 测试端点

### 方法 3: MQTT Broker

如果 AT 固件支持 MQTT AT 指令, 可直接连接 MQTT Broker。

如果固件不支持 MQTT AT 指令, 可:
1. 用一个中间服务器接收 WB3S 的 TCP 数据
2. 服务器端转发到 MQTT / 数据库 / 云平台

## 常用 AT 指令速查

| 指令 | 说明 |
|------|------|
| `AT` | 通信测试 |
| `AT+GMR` | 查询固件版本 |
| `AT+CWMODE=1` | STA 模式 |
| `AT+CWJAP="ssid","pwd"` | 连接 WiFi |
| `AT+CWLAP` | 扫描 WiFi |
| `AT+CIFSR` | 查询 IP/MAC |
| `AT+CIPSTART="TCP","ip",port` | 连接 TCP 服务器 |
| `AT+CIPSEND=<len>` | 发送数据 (指定长度) |
| `AT+CIPMODE=1` | 开启透传模式 |
| `AT+CIPCLOSE` | 关闭 TCP 连接 |
| `AT+CIPSERVER=1,port` | 启动 TCP Server |
| `AT+BLUFI=1` | 开启 SmartConfig 配网 |
| `AT+RESTORE` | 恢复出厂设置 |
| `AT+UART_DEF=9600,8,1,0,0` | 修改波特率 (重启生效) |

## 故障排除

### 1. AT 无响应
- 检查 TX/RX 是否交叉连接 (D1→RXD1, D0→TXD1)
- 检查波特率 115200, 8N1
- 检查供电 3.3V/≥500mA (电源不足是 90% 的问题根源!)
- 复位后等待 1-2 秒, 观察是否打印 "ready"

### 2. WiFi 连不上
- WB3S 仅支持 **2.4GHz** WiFi
- 检查 SSID/密码是否正确
- 尝试 WiFi 无密码测试
- 尝试 SmartConfig 配网 (模式 4)

### 3. TCP 连接失败
- 确保服务器端口可从外网访问
- 先用电脑测试服务器是否可达: `nc -zv host port`
- 检查防火墙

### 4. 模块一直打印乱码
- 确认波特率匹配
- 尝试降低波特率到 9600: `AT+UART_DEF=9600,8,1,0,0` 后重启
- 检查 UART 电平 (3.3V)

### 5. 烧录/更新固件
- 将 TXD (或特定引脚) 拉低上电进入下载模式
- 使用 Beken 原厂烧录工具
- 固件文件: AT_115200_V3.0.7 或更高版本

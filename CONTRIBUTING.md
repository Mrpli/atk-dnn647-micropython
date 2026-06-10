# 贡献指南

感谢您有兴趣为 ATK-DNN647 的 MicroPython 移植版贡献力量！

## 项目定位

本项目基于 MicroPython 官方版本，专为正点原子 ATK-DNN647 开发板添加外设驱动、板级支持以及示例代码。**不接受与 ATK-DNN647 无关的修改**。

---

## 安装 pre-commit

```bash
sudo apt install -y pre-commit

# 在仓库根目录安装钩子
cd ~/atk-dnn647-micropython
pre-commit install
pre-commit install --hook-type commit-msg
```

首次 `git commit` 时会自动下载 ruff、codespell 等工具（仅首次慢，之后秒过）。

---

## 开发流程

### 1. 分支管理

```bash
# 从 main 创建功能分支
git checkout -b feature/your-feature

# 保持分支与 main 同步
git fetch origin
git rebase origin/main
```

### 2. 代码编写

- **C 代码**：遵循 MicroPython 风格，使用 `tools/codeformat.py` 格式化。
- **Python 代码**：遵循 PEP8，使用 ruff 格式化（pre-commit 自动检查）。
- 提交前确保编译通过。

### 3. 提交前检查

每次 `git commit` 时，pre-commit 会**自动对暂存文件**运行以下检查：

| 检查项 | 工具 | 说明 |
|--------|------|------|
| C 代码格式 | `codeformat.py` | 基于 uncrustify |
| Python 代码风格 | ruff | lint + format |
| 拼写检查 | codespell | 检查英文拼写 |
| 提交信息格式 | `verifygitlog.py` | 验证标题行格式 |

> **注意**：pre-commit 默认只检查**你改动的文件（增量）**，不会全仓扫描。
> CI 会**全仓检查**。推送前建议手动全量扫描确保 CI 不出意外：
> ```bash
> pre-commit run --all-files
> ```

### 4. 提交信息规范

格式遵循 MicroPython 官方要求（由 `verifygitlog.py` 强制检查）：

```
<模块路径>: <简短描述，72字符以内>.

<正文段落，每行不超过75字符。>
<正文与标题之间必须有一行空行。>

Signed-off-by: 真实姓名 <邮箱地址>
```

**示例**：

```
stm32/boards/ATK_DNN647: Add I2C5 and SPI5 support.

Enable the I2C5 (PF1/PF0) and SPI5 (PF7/PF9/PF8/PF6) peripherals
for the ATK-DNN647 board. Tested with external I2C sensors and
SPI LCD display.

Signed-off-by: 张三 <zhangsan@example.com>
```

**常见错误**：

| ❌ 错误 | ✅ 正确 |
|---------|---------|
| `模块:描述`（冒号后缺空格） | `模块: 描述` |
| 标题超过 72 字符 | 精简到 72 字符内 |
| 标题后直接写正文（无空行） | 标题和正文间插入空行 |
| Signed-off-by 写 GitHub 昵称 | 写真实姓名 |
| 以 `.` 结尾（MicroPython 要求句号） | 标题以 `.` 结尾 |

> 提示：用 `git commit -s` 自动添加 Signed-off-by 行。

### 5. 推送与 PR

```bash
# 首次推送功能分支
git push -u origin feature/your-feature

# 强制推送（仅限 amend/rebase 后，覆盖自己的分支）
git push --force-with-lease origin feature/your-feature
```

然后在 GitHub 发起 Pull Request，描述清楚：
- 做了什么改动
- 如何测试
- 测试结果（串口日志、LED 闪烁等）

---

## CI 常见失败及修复

| CI 失败信息 | 原因 | 修复 |
|-------------|------|------|
| `codespell` 报拼写错误 | 代码中有英文拼写 typo | 按 CI 日志逐行修正 |
| `ruff-format` 失败 | Python 代码引号/缩进不规范 | `pre-commit run ruff-format -a` 自动修复 |
| `code_formatting` 失败 | C 代码格式不符合 uncrustify 规则 | `tools/codeformat.py -v -c -f` 自动修复 |
| `verifygitlog` 失败 | 提交信息格式不对 | 参考上文提交信息规范 |

---

## 测试要求

- 所有新功能必须在 **ATK-DNN647 开发板** 上实际测试通过。
- 如果修改影响已有外设，请附上测试步骤和结果。

---

## Issue 报告

- 提供开发板型号、固件版本、复现步骤。
- 使用 `.github/ISSUE_TEMPLATE` 中的模板。

---

## 参考

- [MicroPython 贡献者指南](https://github.com/micropython/micropython/wiki/ContributorGuidelines)
- [MicroPython 代码规范](https://github.com/micropython/micropython/blob/master/CODECONVENTIONS.md)
- [Arm GNU Toolchain 下载](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads)

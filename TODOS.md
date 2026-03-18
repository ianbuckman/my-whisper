# TODOs

## P2: 引入 pytest 测试框架

**What:** 创建 `tests/` 目录，引入 pytest，为 `format_shortcut`、`KEYCODE_TO_NAME` 映射表等纯函数写单元测试。

**Why:** 项目零测试，随着功能增多回归风险升高。`format_shortcut` 是纯函数，非常适合作为第一个测试用例。

**Context:** 项目当前 4 个 Python 模块（config, transcriber, app_delegate, hotkey + settings），大部分深度依赖 macOS API（Carbon, AppKit, WebKit），只有少量代码可纯单元测试。建议从纯函数开始，逐步扩展。

**Depends on:** 无

---

## P3: 验证 JS/Python keycode 映射表一致性

**What:** `ui.html` 中的 `CODE_TO_MAC_KEYCODE`（JS event.code → macOS keycode）和 `hotkey.py` 中的 `KEYCODE_TO_NAME`（macOS keycode → 显示名）应覆盖相同的 keycode 范围。

**Why:** 如果 JS 侧支持某个键但 Python 侧没有对应显示名，用户会看到 "Key42" 这样的 fallback 文本。

**Context:** 当前两个表看起来基本一致，但没有自动化验证。可作为引入测试框架后的第一个验证用例。

**Depends on:** P2（测试框架）

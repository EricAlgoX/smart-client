# PySide6 规范

## 项目结构

```
app.py                  → 主窗口（UI 构建 + 布局）
ui/main_controller.py   → 业务逻辑（事件处理、数据流转、告警/记录）
ui/settings_dialog.py   → 设置弹窗
core/                   → 数据层（推理、转换、流、队列）
engine/                 → 引擎层（ONNX、流水线、OCR）
```

## UI 构建方式

**纯代码构建**，不使用 .ui 文件。所有控件在 `app.py` 中创建。

每个面板用独立方法构建：
- `_build_video_area()` → 视频区
- `_build_right_panel()` → 告警 + 统计
- `_build_records_panel()` → 记录表

## 线程模型

```
主线程（UI）:
  ├─ QTimer (33ms) → 读帧 → image_queue
  ├─ result_queue → converter → 显示
  └─ 用户操作 → controller

工作线程:
  ├─ InferenceWorker: image_queue → engine.detect → result_queue
  └─ ImageConverter: result_queue → QImage → Signal → 主线程
```

**规则**：
- 永远不在工作线程更新 UI
- 通过 Signal 跨线程通信
- QThread 用 `wait(毫秒)` 不用 `wait(timeout=毫秒)`

## QSS 管理

- 所有样式在 `resources/style.qss`
- 动态状态用 `setObjectName` + `style().unpolish/polish`
- 不在 Python 代码中 `setStyleSheet`（除动态状态切换外）

## 高 DPI

启动时必须设置：
```python
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)
```

## 工具栏布局

```
[场景选择] | [打开图片] [打开视频] [接入摄像头] | [▶ 开始] [⏹ 停止] | [⚙ 设置]     [v0.0.1]
```

## 状态栏布局

```
● 已连接  |  源: 192.168.1.100  |  场景: 智慧停车  |  2026-06-08 17:00:00
```

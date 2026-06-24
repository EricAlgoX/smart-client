# Smart-Client

基于 PySide6 + ONNX Runtime 的 AI 视觉智能分析客户端，支持多场景、多模型流水线推理。

## 功能特点

- **场景化检测**：每个场景独立配置模型和流水线，按需加载
- **多模型流水线**：支持多步串联推理（如：车辆检测 → 车牌检测 → 车牌 OCR）
- **多源输入**：支持图片、本地视频、RTSP/HTTP 视频流、本地摄像头
- **实时告警**：右侧实时告警流，底部检测记录表，支持 CSV 导出
- **工业风格 UI**：深色毛玻璃主题，自定义标题栏，漂浮粒子动画

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行程序

```bash
python app.py
```

## 使用说明

1. **选择场景**：在工具栏下拉框中选择检测场景
2. **接入输入源**：

| 输入源 | 打开后行为 | 点击「开始检测」后 | 点击「停止」后 |
|--------|-----------|------------------|--------------|
| 📷 图片 | 显示预览 | 推理一次，自动停止 | — |
| 🎬 视频 | 显示首帧 | 推理 + 播放（显示检测结果） | 停止推理 + 停止播放 |
| 📡 摄像头 | 实时画面 | 推理（画面继续播放） | 停止推理，画面继续 |

3. **查看结果**：右侧告警流 + 底部记录表 + 视频画面检测框
4. **导出记录**：点击「导出记录」保存 CSV

## 项目结构

```
smart-client/
├── app.py                          # 主窗口（纯代码 UI，无 .ui 文件）
├── build.py                        # PyInstaller 打包脚本
├── build.spec                      # PyInstaller spec 配置
├── info.py                         # 应用信息（名称、版本、仓库地址）
├── scenes.json                     # 场景配置（场景名 → 模型文件夹映射）
├── requirements.txt                # Python 依赖
│
├── ui/
│   ├── main_controller.py          # 业务逻辑（事件绑定、告警流、记录管理）
│   └── settings_dialog.py          # 设置弹窗（NMS、置信度、超时）
│
├── core/
│   ├── converter.py                # 图像转换 + 检测框绘制（异步线程）
│   ├── inference_worker.py         # 推理工作线程
│   ├── queue.py                    # 全局消息队列（已弃用，保留兼容）
│   ├── stream.py                   # 数据源（图片、视频、摄像头）
│   ├── stream_manager.py           # 多流 Session 管理 + 格子分配
│   └── stream_session.py           # 单个视频流的完整推理管线
│
├── engine/
│   ├── __init__.py                 # 引擎模块标记
│   ├── base.py                     # 引擎抽象基类
│   ├── manager.py                  # 引擎管理器（按场景加载流水线）
│   ├── onnx_engine.py              # ONNX 检测引擎（YOLO letterbox 预处理）
│   ├── pipeline.py                 # 多模型推理流水线
│   ├── plate_ocr_engine.py         # 车牌字符识别引擎（CTC 解码）
│   └── segment_engine.py           # YOLO-Seg 分割引擎（预留扩展）
│
├── models/
│   ├── coco_yolo11n/               # 通用检测场景（COCO 80 类）
│   │   ├── config.json
│   │   └── detect.onnx
│   └── smart_parking/              # 智慧停车场景（车牌检测+OCR）
│       ├── config.json
│       ├── plate_recognition.onnx
│       └── plate_ocr.onnx
│
├── resources/
│   ├── app.ico                     # 应用图标
│   └── style.qss                   # QSS 样式表
│
├── skills/                         # 开发技能文档（设计原则、规范）
│   ├── 01-设计原则.md
│   ├── 02-视觉样式.md
│   ├── 03-动效交互.md
│   ├── 04-质量检查.md
│   └── 05-PySide6规范.md
│
└── utils/
    ├── general.py                  # 通用工具
    ├── logger.py                   # 彩色日志
    └── profiler.py                 # 性能监控
```

## 架构说明

```
┌──────────┐    ┌──────────────┐    ┌───────────────────────────┐
│  数据源   │───▶│  图像队列     │───▶│  推理流水线 (engine)       │
│ (stream) │    │ (queue)      │    │  step1: 检测 → step2: OCR │
└──────────┘    └──────────────┘    └─────────────┬─────────────┘
                                                  │
┌──────────┐    ┌──────────────┐                  │
│  UI 显示  │◀──│  格式转换     │◀─────────────────┘
│(controller)   │ (converter)  │    ┌──────────────┐
└──────────┘    └──────────────┘    │  结果队列     │
                                    │ (queue)      │
                                    └──────────────┘
```

- **数据流**：数据源 → 图像队列 → 推理流水线 → 结果队列 → 格式转换 → UI 显示
- **多线程**：推理、图像转换均在独立 QThread 中执行，不阻塞 UI
- **场景隔离**：每个场景有独立的模型文件夹和配置，互不干扰

## 添加新场景

1. 创建 `models/{场景名}/` 文件夹
2. 放入 `config.json`（定义流水线步骤）和 `.onnx` 模型文件
3. 在 `scenes.json` 加一条记录

```json
// scenes.json
{
  "my_scene": {
    "name": "我的场景",
    "icon": "🔍",
    "description": "场景描述"
  }
}
```

```json
// models/my_scene/config.json
{
    "name": "我的场景",
    "description": "场景描述",
    "pipeline": [
        {
            "step": 1,
            "model": "detect.onnx",
            "role": "detection",
            "input_size": [640, 640],
            "class_names": ["cat", "dog"]
        }
    ],
    "alert_rules": {
        "cat": "info",
        "dog": "warning"
    }
}
```

代码零改动，重启即可。

## 打包发布

```bash
pip install pyinstaller
python build.py
```

输出 `dist/SmartClient/` 文件夹，打包为 zip 发给用户即可：
- 用户解压后双击 `SmartClient.exe` 运行
- 需要 VC++ 运行库（大部分 Windows 已自带）
- 模型文件已内嵌在 `models/` 目录

## 作者

- **EricReno** — christopher0527@163.com

## 开源地址

https://github.com/EricAlgoX/smart-client.git

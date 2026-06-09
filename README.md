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
2. **接入视频源**：点击「打开图片」「打开视频」或「接入摄像头」
3. **开始检测**：点击「▶ 开始检测」
4. **查看结果**：右侧告警流 + 底部记录表 + 视频画面检测框
5. **导出记录**：点击「导出记录」保存 CSV

## 项目结构

```
smart-client/
├── app.py                          # 主窗口（纯代码 UI，无 .ui 文件）
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
│   ├── queue.py                    # 全局消息队列
│   └── stream.py                   # 数据源（图片、视频、摄像头）
│
├── engine/
│   ├── base.py                     # 引擎抽象基类
│   ├── manager.py                  # 引擎管理器（按场景加载流水线）
│   ├── onnx_engine.py              # ONNX 检测引擎（YOLO letterbox 预处理）
│   ├── pipeline.py                 # 多模型推理流水线
│   └── plate_ocr_engine.py         # 车牌字符识别引擎（CTC 解码）
│
├── models/
│   ├── coco_yolo11n/               # 通用检测场景（COCO 80 类）
│   │   ├── config.json
│   │   └── detect.onnx
│   └── smart_parking/              # 智慧停车场景（车辆+车牌+OCR）
│       ├── config.json
│       ├── plate_recognition.onnx
│       ├── plate_ocr.onnx
│       └── vehicle_detection.onnx
│
├── resources/
│   ├── app.ico                     # 应用图标
│   └── style.qss                   # QSS 样式表
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

## 作者

- **EricReno** — christopher0527@163.com

## 开源地址

https://github.com/NeoSmartVision/SmartClient.git

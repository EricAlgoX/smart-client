"""单个视频流的完整推理管线"""

import queue
import threading
from PySide6.QtCore import QThread, Signal
from core.inference_worker import InferenceWorker
from core.converter import ImageConverter
from utils.logger import logger

# 帧率配置
ACTIVE_FPS = 30
BACKGROUND_FPS = 5


class _FrameReaderThread(QThread):
    """后台线程：持续读取帧，放入队列"""
    frame_ready = Signal()

    def __init__(self, video_stream, frame_queue, fps=30):
        super().__init__()
        self.video_stream = video_stream
        self.frame_queue = frame_queue
        self.interval = 1.0 / fps
        self._running = True

    def run(self):
        import time
        while self._running:
            try:
                frame, frame_name = self.video_stream.read()
                if frame is None:
                    self._running = False
                    break
                # 非阻塞放入队列，满了就丢帧
                try:
                    self.frame_queue.put((frame, frame_name), block=False)
                except queue.Full:
                    pass
                self.frame_ready.emit()
                time.sleep(self.interval)
            except Exception:
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.wait(1000)


class StreamSession:
    """封装单个流的完整生命周期"""

    def __init__(self, name: str, video_stream, first_frame, frame_name: str, source_type: str):
        self.name = name
        self.video_stream = video_stream
        self.first_frame = first_frame
        self.frame_name = frame_name
        self.source_type = source_type

        # 帧队列（reader → inference）
        self.frame_queue = queue.Queue(maxsize=5)
        # 推理结果队列（inference → converter）
        self.result_queue = queue.Queue(maxsize=5)

        # 后台帧读取线程
        self._reader_thread = None

        # 推理线程
        self.inference_worker = None

        # 转换线程
        self.converter = None

        # 当前帧
        self.current_frame = first_frame
        self.current_frame_name = frame_name

        # 告警和记录
        self.alerts = []
        self.records = []
        self.alert_count = 0

        # 状态
        self.running = False
        self.is_active = False

    def start_inference(self, confidence=0.3, nms=0.5):
        """启动推理"""
        if self.inference_worker is not None:
            self.inference_worker.stop()

        # background 流降低推理频率，减少对共享引擎的竞争
        skip_frames = 0 if self.is_active else 4  # background: 每5帧推理1帧

        self.inference_worker = InferenceWorker(
            input_queue=self.frame_queue,
            output_queue=self.result_queue,
            confidence=confidence,
            nms=nms,
            skip_frames=skip_frames,
        )
        self.inference_worker.start()

        self.frame_queue.put((self.first_frame, self.frame_name))
        logger.info(f"[Session:{self.name}] 推理已启动 (skip={skip_frames})")

    def stop_inference(self):
        """停止推理"""
        self.running = False
        self._stop_reader()
        if self.inference_worker is not None:
            self.inference_worker.stop()
            self.inference_worker = None
        logger.info(f"[Session:{self.name}] 推理已停止")

    def set_active(self, active: bool):
        """设置是否为活跃流，调整帧率"""
        self.is_active = active
        if self._reader_thread and self._reader_thread.isRunning():
            self._reader_thread.interval = 1.0 / (ACTIVE_FPS if active else BACKGROUND_FPS)

    def start_streaming(self):
        """开始后台读取帧（先停旧线程，再启新的）"""
        if self.source_type in ("video", "camera"):
            self._stop_reader()  # 先停旧线程
            self.running = True
            fps = ACTIVE_FPS if self.is_active else BACKGROUND_FPS
            self._reader_thread = _FrameReaderThread(
                self.video_stream, self.frame_queue, fps=fps
            )
            self._reader_thread.start()

    def _stop_reader(self):
        if self._reader_thread is not None:
            self._reader_thread.stop()
            self._reader_thread = None

    def activate(self, display_callback, get_label_size):
        """激活显示：converter 连接到主显示"""
        self.set_active(True)
        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            self.result_queue,
            get_label_size,
            fps_limit=ACTIVE_FPS,
        )
        self.converter.pixmap_ready.connect(display_callback)
        self.converter.start()

        if self.current_frame is not None:
            self.result_queue.put((self.current_frame, [], self.current_frame_name))

        logger.info(f"[Session:{self.name}] 已激活显示")

    def activate_grid(self, display_callback, get_label_size):
        """Grid 模式激活：converter 输出到指定格子"""
        self.set_active(False)
        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            self.result_queue,
            get_label_size,
            fps_limit=BACKGROUND_FPS,
        )
        self.converter.pixmap_ready.connect(display_callback)
        self.converter.start()

        if self.current_frame is not None:
            self.result_queue.put((self.current_frame, [], self.current_frame_name))

    def deactivate(self):
        """停用显示"""
        self.set_active(False)
        if self.converter is not None:
            self.converter.stop()
        self.converter = None  # 必须清空，否则 _refresh_grid 跳过重建

    def cleanup(self):
        """清理资源（不停 reader，避免同源流的 cv2.VideoCapture 被释放）"""
        self.stop_inference()
        self.deactivate()
        logger.info(f"[Session:{self.name}] 已清理")

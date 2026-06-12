"""单个视频流的完整推理管线"""

import queue
from PySide6.QtCore import QThread, Signal
from core.inference_worker import InferenceWorker
from core.converter import ImageConverter
from utils.logger import logger

# 帧率配置
ACTIVE_FPS = 30
BACKGROUND_FPS = 5


class _FrameReaderThread(QThread):
    """后台线程：持续读取帧，同时放入显示队列和推理队列"""
    frame_ready = Signal()

    def __init__(self, video_stream, display_queue, inference_queue, fps=30):
        super().__init__()
        self.video_stream = video_stream
        self.display_queue = display_queue
        self.inference_queue = inference_queue
        self.interval = 1.0 / fps
        self._running = True

    def run(self):
        import time
        next_time = time.monotonic()
        while self._running:
            try:
                frame, frame_name = self.video_stream.read()
                if frame is None:
                    self._running = False
                    break

                # 帧率控制：基于目标时间点，而非固定 sleep
                now = time.monotonic()
                if now < next_time:
                    # 还没到下一帧的时间，跳过（丢帧保持实时性）
                    continue
                next_time += self.interval
                # 防止累积延迟
                if next_time < now - self.interval:
                    next_time = now

                # 同时放入显示队列和推理队列（满了就丢帧）
                try:
                    self.display_queue.put((frame, frame_name), block=False)
                except queue.Full:
                    pass
                try:
                    self.inference_queue.put((frame, frame_name), block=False)
                except queue.Full:
                    pass
                self.frame_ready.emit()
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

        # 显示队列（reader → converter，实时显示）
        self.display_queue = queue.Queue(maxsize=5)
        # 推理队列（reader → inference worker）
        self.inference_queue = queue.Queue(maxsize=5)
        # 推理结果队列（inference worker → converter，叠加检测框）
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

        skip_frames = 0 if self.is_active else 4

        self.inference_worker = InferenceWorker(
            input_queue=self.inference_queue,
            output_queue=self.result_queue,
            confidence=confidence,
            nms=nms,
            skip_frames=skip_frames,
        )
        self.inference_worker.start()

        # 送入第一帧
        self.inference_queue.put((self.first_frame, self.frame_name))
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
            self._stop_reader()
            self.running = True
            fps = ACTIVE_FPS if self.is_active else BACKGROUND_FPS
            self._reader_thread = _FrameReaderThread(
                self.video_stream, self.display_queue, self.inference_queue, fps=fps
            )
            self._reader_thread.start()

    def _stop_reader(self):
        if self._reader_thread is not None:
            self._reader_thread.stop()
            self._reader_thread = None

    def activate(self, display_callback, get_label_size):
        """激活显示"""
        self.set_active(True)
        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            self.display_queue,
            self.result_queue,
            get_label_size,
            fps_limit=ACTIVE_FPS,
        )
        self.converter.pixmap_ready.connect(display_callback)
        self.converter.start()
        logger.info(f"[Session:{self.name}] 已激活显示")

    def activate_grid(self, display_callback, get_label_size):
        """Grid 模式激活"""
        self.set_active(False)
        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            self.display_queue,
            self.result_queue,
            get_label_size,
            fps_limit=BACKGROUND_FPS,
        )
        self.converter.pixmap_ready.connect(display_callback)
        self.converter.start()

    def deactivate(self):
        """停用显示"""
        self.set_active(False)
        if self.converter is not None:
            self.converter.stop()
        self.converter = None

    def cleanup(self):
        """清理资源（不停 reader，避免同源流的 cv2.VideoCapture 被释放）"""
        self.stop_inference()
        self.deactivate()
        logger.info(f"[Session:{self.name}] 已清理")

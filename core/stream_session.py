"""单个视频流的完整推理管线"""

import queue
import threading
from PySide6.QtCore import QTimer
from core.stream import VideoStream, ImageStream
from core.inference_worker import InferenceWorker
from core.converter import ImageConverter
from utils.logger import logger


class _FrameReader(threading.Thread):
    """后台线程：持续从视频源读取帧，放入最新帧缓冲区"""

    def __init__(self, video_stream, frame_buffer, source_type):
        super().__init__(daemon=True)
        self.video_stream = video_stream
        self.frame_buffer = frame_buffer  # {frame, frame_name, ready}
        self.source_type = source_type
        self._running = True

    def run(self):
        while self._running:
            try:
                frame, frame_name = self.video_stream.read()
                if frame is None:
                    if self.source_type == "image":
                        self._running = False
                    continue
                self.frame_buffer['frame'] = frame
                self.frame_buffer['frame_name'] = frame_name
                self.frame_buffer['ready'] = True
            except Exception as e:
                logger.error(f"[FrameReader] 读取异常: {e}")
                break

    def stop(self):
        self._running = False


class StreamSession:
    """封装单个流的完整生命周期：视频源 → 推理 → 转换 → 显示"""

    def __init__(self, name: str, video_stream, first_frame, frame_name: str, source_type: str):
        self.name = name
        self.video_source = getattr(video_stream, 'video_path', None)
        self.video_stream = video_stream
        self.first_frame = first_frame
        self.frame_name = frame_name
        self.source_type = source_type

        # 每个 session 独立的队列
        self.image_queue = queue.Queue(maxsize=3)
        self.result_queue = queue.Queue(maxsize=3)

        # 推理线程
        self.inference_worker = None

        # 转换线程
        self.converter = None

        # 帧读取线程（后台持续读帧）
        self._frame_buffer = {'frame': first_frame, 'frame_name': frame_name, 'ready': True}
        self._frame_reader = None

        # 分发定时器（主线程，从缓冲区取帧送队列）
        self.timer = QTimer()
        self.timer.timeout.connect(self._dispatch_frame)

        # 当前帧
        self.current_frame = first_frame
        self.current_frame_name = frame_name

        # 告警和记录
        self.alerts = []
        self.records = []
        self.alert_count = 0

        # 状态
        self.running = False

    def start_inference(self, confidence=0.3, nms=0.5):
        """启动推理"""
        if self.inference_worker is not None:
            self.inference_worker.stop()

        self.inference_worker = InferenceWorker(
            input_queue=self.image_queue,
            output_queue=self.result_queue,
            confidence=confidence,
            nms=nms,
        )
        self.inference_worker.start()

        # 送入第一帧（非阻塞）
        try:
            self.image_queue.put_nowait((self.first_frame, self.frame_name))
        except Exception:
            pass

        # 视频/摄像头：启动读帧线程 + 分发定时器
        if self.source_type in ("video", "camera"):
            self.running = True
            if self._frame_reader is None or not self._frame_reader.is_alive():
                self._frame_reader = _FrameReader(self.video_stream, self._frame_buffer, self.source_type)
                self._frame_reader.start()
            self.timer.start(33)

        logger.info(f"[Session:{self.name}] 推理已启动")

    def stop_inference(self):
        """停止推理"""
        self.running = False
        self.timer.stop()
        if self._frame_reader is not None:
            self._frame_reader.stop()
            self._frame_reader = None
        if self.inference_worker is not None:
            self.inference_worker.stop()
            self.inference_worker = None
        logger.info(f"[Session:{self.name}] 推理已停止")

    def _dispatch_frame(self):
        """主线程定时器：从缓冲区取帧，送入队列（不阻塞）"""
        if not self.running:
            return
        if not self._frame_buffer.get('ready'):
            return

        frame = self._frame_buffer['frame']
        frame_name = self._frame_buffer['frame_name']
        self._frame_buffer['ready'] = False

        self.current_frame = frame
        self.current_frame_name = frame_name

        if self.inference_worker is not None:
            try:
                self.image_queue.put_nowait((frame, frame_name))
            except Exception:
                pass  # 队列满则丢弃
        else:
            try:
                self.result_queue.put_nowait((frame, [], frame_name))
            except Exception:
                pass

    def activate(self, display_callback, get_label_size):
        """激活显示：converter 连接到主显示"""
        if self.converter is not None:
            self.converter.stop()

        self.converter = ImageConverter(
            self.result_queue,
            get_label_size,
            fps_limit=20,
        )
        self.converter.pixmap_ready.connect(display_callback)
        self.converter.start()

        # 显示当前帧（非阻塞）
        if self.current_frame is not None:
            try:
                self.result_queue.put_nowait((self.current_frame, [], self.current_frame_name))
            except Exception:
                pass

        # 如果是视频/摄像头，确保读帧线程在运行
        if self.source_type in ("video", "camera") and self.running:
            if self._frame_reader is None or not self._frame_reader.is_alive():
                self._frame_reader = _FrameReader(self.video_stream, self._frame_buffer, self.source_type)
                self._frame_reader.start()
            if not self.timer.isActive():
                self.timer.start(33)

        logger.info(f"[Session:{self.name}] 已激活显示")

    def deactivate(self):
        """停用显示：converter 断开"""
        if self.converter is not None:
            self.converter.stop()
            self.converter = None

    def cleanup(self):
        """清理所有资源"""
        self.stop_inference()
        self.deactivate()
        logger.info(f"[Session:{self.name}] 已清理")

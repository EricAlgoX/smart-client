import cv2
import queue
import traceback
from PySide6.QtGui import QImage
from PySide6.QtCore import Signal, QThread
from core.visualizer import Visualizer


class ImageConverter(QThread):
    """
    后台线程：把 BGR numpy frame 转换为 QPixmap（并做必要的 resize）
    输入通过 input_queue（thread-safe），输出通过信号发回主线程
    """
    pixmap_ready = Signal(QImage, object, str, object)  # (qimage, details, path, original_rgb)

    def __init__(self, input_queue: queue.Queue, target_size_getter, fps_limit=30):
        super().__init__()
        self.input_queue = input_queue
        self._running = True
        self.target_size_getter = target_size_getter  # function to get current QLabel size (QSize)
        self.fps_limit = fps_limit
        self.min_interval = 1.0 / fps_limit if fps_limit > 0 else 0
        self.viz = Visualizer()  # 添加 visualizer

    def run(self):
        import time
        while self._running:
            try:
                start = time.time()
                item = self.input_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                frame, details, path = item
                # 安全检查
                if frame is None:
                    continue

                # 直接在原图上绘制，不复制
                for det in details:
                    if 'bbox' in det:
                        xmin, ymin, xmax, ymax = det['bbox']
                        class_name = det.get('class', '')
                        score = det.get('score', '')
                        frame = self.viz.draw_boxes_fast(frame, xmin, ymin, xmax, ymax, class_name, score)

                # 转换 BGR->RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                original_rgb = rgb  # 保存引用，不复制

                target_size = self.target_size_getter()
                if target_size is not None and not target_size.isEmpty():
                    display_rgb = cv2.resize(rgb, (target_size.width(), target_size.height()), interpolation=cv2.INTER_LINEAR)
                else:
                    display_rgb = rgb

                h, w, ch = display_rgb.shape
                bytes_per_line = ch * w
                qimg = QImage(display_rgb.copy().data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

                # 发送给主线程
                self.pixmap_ready.emit(qimg, details, path, original_rgb)

            except Exception:
                traceback.print_exc()

    def stop(self):
        self._running = False
        self.wait(timeout=500)

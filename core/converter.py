import cv2
import queue
import traceback
from PySide6.QtGui import QImage
from PySide6.QtCore import Signal, QThread


def draw_box(image, xmin, ymin, xmax, ymax, class_name, score, text=""):
    """在图像上绘制检测框和标签"""
    cv2.rectangle(image, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
    label = text if text else (f"{class_name} {float(score):.2f}" if score else class_name)
    cv2.putText(image, label, (xmin, ymin - 5),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return image


class ImageConverter(QThread):
    """后台线程：BGR frame → QImage，叠加检测框"""
    pixmap_ready = Signal(QImage, object, str, object)

    def __init__(self, input_queue: queue.Queue, target_size_getter, fps_limit=30):
        super().__init__()
        self.input_queue = input_queue
        self._running = True
        self.target_size_getter = target_size_getter
        self.fps_limit = fps_limit

    def run(self):
        while self._running:
            try:
                item = self.input_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                frame, details, path = item
                if frame is None:
                    continue

                # 绘制检测框
                for det in details:
                    if 'bbox' in det:
                        xmin, ymin, xmax, ymax = det['bbox']
                        frame = draw_box(frame, xmin, ymin, xmax, ymax,
                                        det.get('class', ''), det.get('score', ''),
                                        text=det.get('text', ''))

                # BGR → RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                target_size = self.target_size_getter()
                if target_size is not None and not target_size.isEmpty():
                    display_rgb = cv2.resize(rgb, (target_size.width(), target_size.height()),
                                            interpolation=cv2.INTER_LINEAR)
                else:
                    display_rgb = rgb

                h, w, ch = display_rgb.shape
                qimg = QImage(display_rgb.copy().data, w, h, ch * w, QImage.Format.Format_RGB888)
                self.pixmap_ready.emit(qimg, details, path, rgb)

            except Exception:
                traceback.print_exc()

    def stop(self):
        self._running = False
        self.wait(500)

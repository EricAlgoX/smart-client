import cv2
import time
import queue
import traceback
from PySide6.QtGui import QImage
from PySide6.QtCore import Signal, QThread


# 类别颜色缓存（自动生成，保证同一类别颜色一致）
_class_color_cache = {}


def _get_class_color(class_name: str) -> tuple:
    """根据类别名自动生成颜色（HSV 均匀分布，保证区分度）"""
    if class_name not in _class_color_cache:
        idx = len(_class_color_cache)
        # 用黄金比例均匀分布色相，饱和度和亮度固定
        hue = int((idx * 137.508) % 360)  # 黄金角
        # HSV → BGR
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.75, 0.95)
        _class_color_cache[class_name] = (int(b * 255), int(g * 255), int(r * 255))
    return _class_color_cache[class_name]


def draw_box(image, xmin, ymin, xmax, ymax, class_name, score, text=""):
    """工业风格检测框：角标 + 半透明填充 + 圆角药丸标签"""
    color = _get_class_color(class_name)
    h, w = image.shape[:2]
    xmin, ymin = max(0, xmin), max(0, ymin)
    xmax, ymax = min(w, xmax), min(h, ymax)
    bw, bh = xmax - xmin, ymax - ymin
    if bw <= 0 or bh <= 0:
        return image

    # 1. 半透明填充（10% 不透明度）
    overlay = image.copy()
    cv2.rectangle(overlay, (xmin, ymin), (xmax, ymax), color, -1)
    cv2.addWeighted(overlay, 0.1, image, 0.9, 0, image)

    # 2. 角标框（四角 L 形标记，不画完整矩形）
    corner_len = min(20, bw // 4, bh // 4)
    thickness = 2
    # 左上
    cv2.line(image, (xmin, ymin), (xmin + corner_len, ymin), color, thickness)
    cv2.line(image, (xmin, ymin), (xmin, ymin + corner_len), color, thickness)
    # 右上
    cv2.line(image, (xmax, ymin), (xmax - corner_len, ymin), color, thickness)
    cv2.line(image, (xmax, ymin), (xmax, ymin + corner_len), color, thickness)
    # 左下
    cv2.line(image, (xmin, ymax), (xmin + corner_len, ymax), color, thickness)
    cv2.line(image, (xmin, ymax), (xmin, ymax - corner_len), color, thickness)
    # 右下
    cv2.line(image, (xmax, ymax), (xmax - corner_len, ymax), color, thickness)
    cv2.line(image, (xmax, ymax), (xmax, ymax - corner_len), color, thickness)

    # 3. 圆角药丸标签
    label = text if text else (f"{class_name} {float(score):.2f}" if score else class_name)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    (tw, th), _ = cv2.getTextSize(label, font, font_scale, 1)
    pill_w = tw + 12
    pill_h = th + 8
    pill_x = xmin
    pill_y = ymin - pill_h - 4

    # 药丸背景（圆角矩形）
    pill_r = 4
    cv2.rectangle(image, (pill_x + pill_r, pill_y), (pill_x + pill_w - pill_r, pill_y + pill_h), color, -1)
    cv2.rectangle(image, (pill_x, pill_y + pill_r), (pill_x + pill_w, pill_y + pill_h - pill_r), color, -1)
    cv2.circle(image, (pill_x + pill_r, pill_y + pill_r), pill_r, color, -1)
    cv2.circle(image, (pill_x + pill_w - pill_r, pill_y + pill_r), pill_r, color, -1)
    cv2.circle(image, (pill_x + pill_r, pill_y + pill_h - pill_r), pill_r, color, -1)
    cv2.circle(image, (pill_x + pill_w - pill_r, pill_y + pill_h - pill_r), pill_r, color, -1)

    # 文字
    cv2.putText(image, label, (pill_x + 6, pill_y + th + 2),
                font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

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
        import logging
        logger = logging.getLogger("Smart-Client")
        min_interval = 1.0 / self.fps_limit if self.fps_limit > 0 else 0
        last_emit = 0.0
        frame_count = 0

        while self._running:
            try:
                item = self.input_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            try:
                # 帧率限制：跳过过快的帧
                now = time.monotonic()
                if now - last_emit < min_interval:
                    continue
                last_emit = now

                frame, details, path = item
                if frame is None:
                    continue

                frame_count += 1
                if frame_count == 1:
                    logger.info(f"[Converter] 首帧处理, shape={frame.shape}")

                # 绘制分割 mask（半透明叠加）
                for det in details:
                    if 'mask' in det and det['mask'] is not None:
                        mask = det['mask']
                        if mask.shape[:2] == frame.shape[:2]:
                            color = _get_class_color(det.get('class', ''))
                            overlay = frame.copy()
                            overlay[mask > 0] = color
                            frame = cv2.addWeighted(overlay, 0.35, frame, 0.65, 0)

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
        # 断开信号，防止旧信号指向已删除的格子
        try:
            self.pixmap_ready.disconnect()
        except RuntimeError:
            pass
        self.wait(2000)

import cv2
import time
import queue
from collections import deque
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
    """工业风格检测框：角标 + 圆角药丸标签（半透明填充由调用方统一处理）"""
    color = _get_class_color(class_name)
    h, w = image.shape[:2]
    xmin, ymin = max(0, xmin), max(0, ymin)
    xmax, ymax = min(w, xmax), min(h, ymax)
    bw, bh = xmax - xmin, ymax - ymin
    if bw <= 0 or bh <= 0:
        return image

    # 1. 角标框（四角 L 形标记，不画完整矩形）
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
    """后台线程：实时显示视频帧 + 异步叠加检测结果

    数据流：
      frame_queue → 显示帧（实时，不阻塞）
      result_queue → 更新检测结果（异步，叠加到下一帧）
    """
    pixmap_ready = Signal(QImage, object, str, object)

    def __init__(self, frame_queue: queue.Queue, result_queue: queue.Queue,
                 target_size_getter, fps_limit=30, buffer_size=3):
        super().__init__()
        self.frame_queue = frame_queue
        self.result_queue = result_queue
        self._running = True
        self.target_size_getter = target_size_getter
        self.fps_limit = fps_limit
        self._cached_details = []
        self._last_frame = None  # 缓存最后一帧，推理结果到达时重新显示
        self._last_path = ""
        # 帧缓冲：延迟 buffer_size 帧显示，等待推理结果同步
        self._frame_buffer = deque(maxlen=buffer_size)

    def run(self):
        import logging
        logger = logging.getLogger("Smart-Client")
        min_interval = 1.0 / self.fps_limit if self.fps_limit > 0 else 0
        last_emit = 0.0
        frame_count = 0
        while self._running:
            # 1. 非阻塞读取推理结果，检测是否更新
            details_updated = False
            try:
                while True:
                    _, details, _ = self.result_queue.get_nowait()
                    if details is not None:
                        self._cached_details = details
                        details_updated = True
            except queue.Empty:
                pass

            # 2. 读取原始帧到缓冲区
            try:
                frame, path = self.frame_queue.get(timeout=0.05)
                if frame is not None:
                    self._frame_buffer.append((frame, path))
                    self._last_frame = frame
                    self._last_path = path
            except queue.Empty:
                pass

            # 3. 推理结果更新 + 有缓存帧 → 重新显示（图片模式的关键）
            if details_updated and self._last_frame is not None:
                self._emit_frame(self._last_frame.copy(), self._cached_details, self._last_path)
                continue

            # 4. 从缓冲区取出最早的一帧显示
            if not self._frame_buffer:
                continue

            frame, path = self._frame_buffer[0]

            # 帧率限制
            now = time.monotonic()
            if now - last_emit < min_interval:
                continue
            last_emit = now

            frame_count += 1
            if frame_count == 1:
                logger.info(f"[Converter] 首帧处理, shape={frame.shape}, 缓冲={self._frame_buffer.maxlen}帧")

            self._emit_frame(frame, self._cached_details, path)

    def _emit_frame(self, frame, details, path):
        """绘制检测框并发射信号"""
        # 绘制分割 mask
        for det in details:
            if 'mask' in det and det['mask'] is not None:
                mask = det['mask']
                if mask.shape[:2] == frame.shape[:2]:
                    color = _get_class_color(det.get('class', ''))
                    overlay = frame.copy()
                    overlay[mask > 0] = color
                    frame = cv2.addWeighted(overlay, 0.35, frame, 0.65, 0)

        # 半透明填充
        if details:
            overlay = frame.copy()
            has_overlay = False
            for det in details:
                if 'bbox' in det:
                    xmin, ymin, xmax, ymax = det['bbox']
                    color = _get_class_color(det.get('class', ''))
                    cv2.rectangle(overlay, (xmin, ymin), (xmax, ymax), color, -1)
                    has_overlay = True
            if has_overlay:
                frame = cv2.addWeighted(overlay, 0.1, frame, 0.9, 0)

        # 检测框和标签
        for det in details:
            if 'bbox' in det:
                xmin, ymin, xmax, ymax = det['bbox']
                frame = draw_box(frame, xmin, ymin, xmax, ymax,
                                det.get('class', ''), det.get('score', ''),
                                text=det.get('text', ''))

        # BGR → RGB → QImage
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

    def stop(self):
        self._running = False
        try:
            self.pixmap_ready.disconnect()
        except RuntimeError:
            pass
        self.wait(2000)

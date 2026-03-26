# visualizer.py
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class Visualizer:
    def __init__(self):
        self._font_cache = {}

    # -------------------------------
    # 内部方法：获取中文字体（带缓存）
    # -------------------------------
    def _get_chinese_font(self, font_size: int):
        if font_size in self._font_cache:
            return self._font_cache[font_size]

        candidate_paths = [
            r"C:\\Windows\\Fonts\\msyh.ttc",
            r"C:\\Windows\\Fonts\\msyh.ttf",
            r"C:\\Windows\\Fonts\\simhei.ttf",
            r"C:\\Windows\\Fonts\\simsun.ttc",
        ]
        for path in candidate_paths:
            try:
                font = ImageFont.truetype(path, font_size)
                self._font_cache[font_size] = font
                return font
            except Exception:
                continue

        font = ImageFont.load_default()
        self._font_cache[font_size] = font
        return font

    # -------------------------------
    # 内部方法：PIL 绘制中文
    # -------------------------------
    def _put_text_cn(self, image_bgr, text, org, font_size=20, color_bgr=(255, 255, 255)):
        x, y = org
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(image_rgb)
        draw = ImageDraw.Draw(pil_img)
        font = self._get_chinese_font(font_size)
        color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
        draw.text((x, y), text, font=font, fill=color_rgb)

        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    # -------------------------------
    # 绘制检测框（快速版本，使用 OpenCV）
    # -------------------------------
    def draw_boxes_fast(self, image, xmin, ymin, xmax, ymax, class_name, score, box_color=(0, 255, 0)):
        # 绘制框
        cv2.rectangle(image, (xmin, ymin), (xmax, ymax), box_color, 2)

        # 使用 OpenCV 绘制文字（不支持中文，但速度快）
        label = f"{class_name} {float(score):.2f}" if score else class_name
        cv2.putText(image, label, (xmin, ymin - 5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return image

    # -------------------------------
    # 绘制推理时间（带背景条）
    # -------------------------------
    def draw_elapsed_time(self, image_bgr, elapsed_ms: float, x=50, y=40):
        """
        elapsed_ms: 毫秒数(float)
        在左上角显示一个黑底白字的小条
        """
        text = f"{int(elapsed_ms*1000):4d} ms"

        # --- 背景条: 半透明 ---
        overlay = image_bgr.copy()
        cv2.rectangle(overlay, (x - 10, y - 25), (x + 120, y + 10), (0, 0, 0), -1)

        # 透明度
        alpha = 0.5
        image = cv2.addWeighted(overlay, alpha, image_bgr, 1 - alpha, 0)

        # --- 文字（白色） ---
        cv2.putText(
            image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
            0.8, (255, 255, 255), 2, cv2.LINE_AA
        )

        return image

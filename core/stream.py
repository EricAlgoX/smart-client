import os
import cv2
import time
from utils.logger import logger

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QFileDialog, QInputDialog


def resize(frame):
    """检查图片尺寸，如果超过1920x1080则按比例缩放"""
    height, width = frame.shape[:2]
    if width <= 1920 and height <= 1080:
        return frame
    scale = min(1920 / width, 1080 / height)
    return cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)


# ══════════════════════════════════════════════
#  数据源类
# ══════════════════════════════════════════════

class ImageStream:
    def __init__(self, source=0):
        self.image_path = source

    def read(self):
        if not os.path.exists(self.image_path):
            return None, None
        basename = os.path.basename(self.image_path).lower()
        if not basename.endswith(('.jpg', '.jpeg', '.png', '.bmp')):
            return None, None
        frame = cv2.imread(self.image_path)
        if frame is None:
            return None, None
        return resize(frame), self.image_path


class VideoStream:
    def __init__(self, source=0):
        self.video_path = source
        self.cap = None

        # 根据源类型选择后端：本地摄像头用 DShow，网络流用 FFmpeg
        if isinstance(source, int):
            # 本地摄像头：优先 DirectShow（Windows 兼容性最好）
            self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                # 回退到默认后端
                self.cap = cv2.VideoCapture(source)
        else:
            # 网络流/文件：用 FFmpeg
            self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频源：{source}")
        self.is_video = True

    def read(self, retries=3):
        for _ in range(retries):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                image_name = os.path.join('images', time.strftime("%Y%m%d_%H%M%S", time.localtime()) + '.jpg')
                return resize(frame), image_name
            time.sleep(0.01)
        return None, None

    def release(self):
        self.cap.release()


class FolderStream:
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.image_files = []
        self.current_index = 0
        self.is_video = False
        supported_formats = ('.jpg', '.jpeg', '.png', '.bmp')
        for file_name in os.listdir(folder_path):
            if file_name.lower().endswith(supported_formats):
                self.image_files.append(os.path.join(folder_path, file_name))
        self.image_files.sort()
        logger.info(f"文件夹中找到 {len(self.image_files)} 张图片")

    def read(self):
        if not self.image_files or self.current_index >= len(self.image_files):
            return None, None
        image_path = self.image_files[self.current_index]
        frame = cv2.imread(image_path)
        if frame is not None:
            frame = resize(frame)
        if not self.next():
            return None, None
        return frame, image_path

    def next(self):
        if self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            return True
        else:
            self.reset()
            return False

    def reset(self):
        self.current_index = 0


# ══════════════════════════════════════════════
#  后台连接线程（解决 RTSP 连接卡 UI 的问题）
# ══════════════════════════════════════════════

class _StreamConnectWorker(QThread):
    """后台线程：打开视频流并读取第一帧，完成后通过信号通知主线程"""
    finished = Signal(object, object, str)  # (stream, frame, frame_name)
    error = Signal(str)

    def __init__(self, source, source_name):
        super().__init__()
        self.source = source
        self.source_name = str(source_name)

    def run(self):
        try:
            logger.info(f"[StreamWorker] 正在打开视频源: {self.source} (类型: {type(self.source).__name__})")
            stream = VideoStream(self.source)
            logger.info(f"[StreamWorker] 视频源已打开，正在读取第一帧...")
            frame, frame_name = stream.read()
            if frame is None:
                self.error.emit("无法读取视频帧，请检查摄像头是否被其他程序占用")
                self.quit()
                return
            logger.info(f"[StreamWorker] 第一帧读取成功: {frame.shape}")
            self.finished.emit(stream, frame, frame_name or self.source_name)
        except Exception as e:
            logger.error(f"[StreamWorker] 连接失败: {e}")
            self.error.emit(str(e))
        finally:
            self.quit()


# ══════════════════════════════════════════════
#  选择函数（同步，返回 dict 或 None）
# ══════════════════════════════════════════════

def select_image(self):
    try:
        file_name, _ = QFileDialog.getOpenFileName(
            self.window, "选择图片", "",
            "图像文件 (*.png *.jpg *.jpeg *.bmp *.gif)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not file_name:
            return None
        stream = ImageStream(file_name)
        frame, frame_name = stream.read()
        if frame is None:
            return None
        return {'stream': stream, 'stream_name': file_name, 'frame': frame, 'frame_name': frame_name}
    except Exception as e:
        logger.error(f"选择图片时出错: {e}")
        return None


def select_video(self):
    try:
        video_name, _ = QFileDialog.getOpenFileName(
            self.window, "选择视频", "",
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not video_name:
            return None
        stream = VideoStream(video_name)
        frame, frame_name = stream.read()
        if frame is None:
            return None
        return {'stream': stream, 'stream_name': video_name, 'frame': frame, 'frame_name': frame_name}
    except Exception as e:
        logger.error(f"选择视频时出错: {e}")
        return None


def select_folder(self):
    try:
        folder_name = QFileDialog.getExistingDirectory(
            self.window, "选择文件夹", "",
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog
        )
        if not folder_name:
            return None
        stream = FolderStream(folder_name)
        frame, frame_name = stream.read()
        if frame is None:
            logger.warning("文件夹中没有图片")
            return None
        return {'stream': stream, 'stream_name': folder_name, 'frame': frame, 'frame_name': frame_name}
    except Exception as e:
        logger.error(f"选择文件夹时出错: {e}")
        return None


def select_stream(self):
    options = ["本地摄像头", "RTSP/HTTP 地址", "取消"]
    choice, ok = QInputDialog.getItem(
        self.window, "选择实时流来源", "请选择:", options, 0, False
    )
    if not ok or choice == "取消":
        logger.info("[select_stream] 用户取消")
        return None

    try:
        if choice == "本地摄像头":
            index, ok = QInputDialog.getInt(
                self.window, "摄像头索引",
                "输入摄像头索引（通常为0或1）:", 0, 0, 10, 1
            )
            if not ok:
                return None
            source = index
            logger.info(f"[select_stream] 本地摄像头索引={source}, 类型={type(source).__name__}")
        else:
            url, ok = QInputDialog.getText(
                self.window, "输入流地址",
                "请输入 RTSP/HTTP 流地址:",
                text="rtsp://admin:password@192.168.1.100:554"
            )
            if not ok:
                return None
            source = url
            logger.info(f"[select_stream] 网络流={source}")

        if source is None or source == "":
            logger.warning("[select_stream] source 为空")
            return None

        worker = _StreamConnectWorker(source, source)
        logger.info(f"[select_stream] 创建worker, source={source}, type={type(source).__name__}")
        return {'worker': worker, 'stream_name': str(source)}

    except Exception as e:
        logger.error(f"选择实时流时出错: {e}")
        return None

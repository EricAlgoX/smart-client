import sys
import random
import logging
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QBrush, QIcon

from utils.logger import logger
from utils.general import gradient_text
from core.server import stop_all_servers
from controller.main_controller import MainController
from info import __appname__, __preferred_device__, __url__, __version__

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart-Client")
        # 设置窗口图标（ico 或 png 均可）
        self.setWindowIcon(QIcon("resources/app.ico"))

        # 直接加载 ui 文件
        uic.loadUi("ui/mainwindow.ui", self)
            
        self.controller = MainController(self)
        
        # 动态主题
        
        # 渐变颜色相位
        self.phase = 0
        # 圆点数据 [x, y, 半径, x速度, y速度]`909`
        self.dots = [
            [random.randint(0, 1280),
             random.randint(0, 720),
             random.randint(5, 15),
             random.uniform(-0.5, 0.5),
             random.uniform(-0.5, 0.5)]
            for _ in range(66)
        ]
        # 定时器刷新动画
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(30)  # 每 30ms 刷新一次（约 33fps）
    
    def update_animation(self):
        # 更新圆点位置
        for dot in self.dots:
            dot[0] += dot[3]
            dot[1] += dot[4]

            # 边界反弹
            if dot[0] < 0 or dot[0] > self.width():
                dot[3] *= -1
            if dot[1] < 0 or dot[1] > self.height():
                dot[4] *= -1

        # 渐变相位更新
        self.phase += 0.01
        self.update()  # 触发重绘

    def paintEvent(self, event):
        painter = QPainter(self)

        # # ===== 1. 绘制渐变背景 =====
        # gradient = QLinearGradient(0, 0, self.width(), self.height())
        # color1 = QColor.fromHsv(int((self.phase * 50) % 360), 200, 255)
        # color2 = QColor.fromHsv(int((self.phase * 50 + 120) % 360), 200, 255)
        # gradient.setColorAt(0, color1)
        # gradient.setColorAt(1, color2)
        # painter.fillRect(self.rect(), gradient)

        # ===== 2. 绘制漂浮圆点 =====
        painter.setRenderHint(QPainter.Antialiasing)
        for dot in self.dots:
            painter.setBrush(QBrush(QColor(255, 255, 255, 100)))  # 半透明白色
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(dot[0]), int(dot[1]), int(dot[2]), int(dot[2]))

def main():
    try:
        logger.setLevel(getattr(logging, "INFO"))
        logger.info(
            f"🚀 {gradient_text(f'Smart-Client v{__version__} launched!')}"
        )

        logger.info(f"⭐ If you like it, give us a star: {__url__}")

        app = QtWidgets.QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    finally:
        stop_all_servers()
if __name__ == "__main__":
    main()
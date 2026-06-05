import sys
import math
import random
import logging
from datetime import datetime
from PySide6 import QtCore
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QSlider, QTableWidget, QTableWidgetItem,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QToolBar,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QMessageBox, QApplication, QStatusBar,
)

from utils.logger import logger
from utils.general import gradient_text
from core.server import stop_all_servers
from controller.main_controller import MainController
from info import __appname__, __preferred_device__, __url__, __version__


# ── 漂浮粒子背景 ──
class ParticleBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dots = []
        self._init_dots(35)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _init_dots(self, n):
        for _ in range(n):
            self.dots.append({
                'x': random.uniform(0, 1920), 'y': random.uniform(0, 1080),
                'r': random.uniform(2, 5),
                'vx': random.uniform(-0.25, 0.25), 'vy': random.uniform(-0.15, 0.15),
                'alpha': random.uniform(12, 40),
                'hue': random.randint(190, 220),
                'phase': random.uniform(0, 6.28),
            })

    def _tick(self):
        w, h = self.width(), self.height()
        for d in self.dots:
            d['x'] += d['vx']
            d['y'] += d['vy']
            d['phase'] += 0.02
            if d['x'] < -10 or d['x'] > w + 10:
                d['vx'] *= -1
            if d['y'] < -10 or d['y'] > h + 10:
                d['vy'] *= -1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for d in self.dots:
            breathe = d['alpha'] + 8 * (0.5 + 0.5 * math.sin(d['phase']))
            color = QColor.fromHsv(d['hue'], 80, 200, int(breathe))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(d['x']), int(d['y']), int(d['r']), int(d['r']))
        painter.end()


# ══════════════════════════════════════════════
#  MainWindow — 产品通版主界面
# ══════════════════════════════════════════════
class MainWindow(QMainWindow):
    """Smart-Client 通版主界面"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__appname__} v{__version__}")
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)
        self.setWindowIcon(QIcon("resources/app.ico"))

        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()

        self._load_stylesheet()

        # 日志桥接：controller 中 log_edit.append(msg) 会转发到 logger + 状态栏
        self.log_edit = self._LogBridge(self)

        self.controller = MainController(self)

        # 粒子背景
        self.particle_bg = ParticleBackground(self.centralWidget())
        self.particle_bg.lower()
        self.centralWidget().installEventFilter(self)

    # ────────────────────────────────────────
    #  UI 构建
    # ────────────────────────────────────────
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # 主分割器：上(视频+告警) + 下(记录)
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setHandleWidth(3)

        # 上部分：左(视频) + 右(告警+统计)
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setHandleWidth(3)
        top_splitter.addWidget(self._build_video_area())
        top_splitter.addWidget(self._build_right_panel())
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setSizes([1100, 320])

        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(self._build_records_panel())
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        main_splitter.setSizes([650, 180])

        main_layout.addWidget(main_splitter)

    # ── 视频区域 ──
    def _build_video_area(self):
        container = QWidget()
        container.setObjectName("videoContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # 视频画面
        self.label = QLabel()
        self.label.setObjectName("videoLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(640, 360)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.label)

        # 空状态占位
        self.placeholderWidget = QWidget()
        self.placeholderWidget.setObjectName("placeholderWidget")
        ph_layout = QVBoxLayout(self.placeholderWidget)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_icon = QLabel("📹")
        ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_icon.setStyleSheet("font-size: 52px; background: transparent; border: none;")
        ph_title = SmartLabel("等待接入视频源")
        ph_title.setObjectName("placeholderTitle")
        ph_hint = SmartLabel("点击上方「接入摄像头」或「打开图片」开始")
        ph_hint.setObjectName("placeholderHint")

        ph_layout.addStretch()
        ph_layout.addWidget(ph_icon)
        ph_layout.addSpacing(10)
        ph_layout.addWidget(ph_title)
        ph_layout.addSpacing(4)
        ph_layout.addWidget(ph_hint)
        ph_layout.addStretch()

        layout.addWidget(self.placeholderWidget)
        self.label.hide()

        return container

    # ── 右侧面板：告警 + 统计 ──
    def _build_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 实时告警
        alert_group = QGroupBox("实时告警")
        alert_group.setObjectName("alertGroup")
        alert_layout = QVBoxLayout(alert_group)
        alert_layout.setContentsMargins(6, 14, 6, 6)

        self.alertList = QTreeWidget()
        self.alertList.setHeaderLabels(["时间", "级别", "详情"])
        self.alertList.setObjectName("alertList")
        self.alertList.setRootIsDecorated(False)
        self.alertList.setAlternatingRowColors(True)
        self.alertList.header().resizeSection(0, 70)
        self.alertList.header().resizeSection(1, 50)
        self.alertList.header().setStretchLastSection(True)
        alert_layout.addWidget(self.alertList)

        layout.addWidget(alert_group, 1)

        # 统计卡片
        stats_group = QGroupBox("检测统计")
        stats_group.setObjectName("statsGroup")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setContentsMargins(8, 16, 8, 8)
        stats_layout.setSpacing(8)

        self.statsCountLabel = SmartLabel("0")
        self.statsCountLabel.setObjectName("statsValue")
        self.statsAlertLabel = SmartLabel("0")
        self.statsAlertLabel.setObjectName("statsValue")
        self.statsFpsLabel = SmartLabel("--")
        self.statsFpsLabel.setObjectName("statsValue")
        self.statsSceneLabel = SmartLabel("未选择")
        self.statsSceneLabel.setObjectName("statsValue")

        for row, (name, widget) in enumerate([
            ("检测目标", self.statsCountLabel),
            ("今日告警", self.statsAlertLabel),
            ("当前帧率", self.statsFpsLabel),
            ("当前场景", self.statsSceneLabel),
        ]):
            lbl = SmartLabel(name)
            lbl.setObjectName("statsKey")
            stats_layout.addWidget(lbl, row, 0)
            stats_layout.addWidget(widget, row, 1)

        layout.addWidget(stats_group)
        return panel

    # ── 底部：检测记录 ──
    def _build_records_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(4, 0, 4, 0)
        title = SmartLabel("检测记录")
        title.setObjectName("recordTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.btnExportRecords = QPushButton("导出记录")
        self.btnExportRecords.setObjectName("secondaryBtn")
        self.btnExportRecords.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(self.btnExportRecords)

        layout.addWidget(header)

        self.recordTable = QTableWidget(0, 5)
        self.recordTable.setObjectName("recordTable")
        self.recordTable.setHorizontalHeaderLabels(["时间", "场景", "类型", "详情", "截图"])
        self.recordTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.recordTable.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.recordTable.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.recordTable.setColumnWidth(0, 80)
        self.recordTable.setColumnWidth(4, 50)
        self.recordTable.verticalHeader().setDefaultSectionSize(24)
        self.recordTable.setAlternatingRowColors(True)
        self.recordTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.recordTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.recordTable.setMaximumHeight(200)
        layout.addWidget(self.recordTable)

        return panel

    # ────────────────────────────────────────
    #  工具栏
    # ────────────────────────────────────────
    def _setup_toolbar(self):
        toolbar = QToolBar()
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        # 场景选择
        scene_label = SmartLabel("  场景: ")
        scene_label.setObjectName("toolbarLabel")
        toolbar.addWidget(scene_label)

        self.sceneBox = QComboBox()
        self.sceneBox.setObjectName("sceneBox")
        self.sceneBox.setMinimumWidth(130)
        toolbar.addWidget(self.sceneBox)

        toolbar.addSeparator()

        # 源操作
        self.tb_act_image = QAction("打开图片", self)
        self.tb_act_camera = QAction("接入摄像头", self)
        toolbar.addAction(self.tb_act_image)
        toolbar.addAction(self.tb_act_camera)

        toolbar.addSeparator()

        # 推理控制
        self.tb_act_start = QAction("▶  开始检测", self)
        self.tb_act_stop = QAction("⏹  停止", self)
        toolbar.addAction(self.tb_act_start)
        toolbar.addAction(self.tb_act_stop)

        toolbar.addSeparator()

        # 设置
        self.tb_act_settings = QAction("⚙  设置", self)
        toolbar.addAction(self.tb_act_settings)

        # 右侧版本号
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        ver_label = SmartLabel(f"v{__version__}")
        ver_label.setObjectName("versionLabel")
        toolbar.addWidget(ver_label)

    # ────────────────────────────────────────
    #  状态栏
    # ────────────────────────────────────────
    def _setup_statusbar(self):
        statusbar = QStatusBar()
        statusbar.setObjectName("statusBar")
        self.setStatusBar(statusbar)

        self.statusDot = SmartLabel("●")
        self.statusDot.setObjectName("statusDotRed")
        self.statusSourceLabel = SmartLabel("未连接")
        self.statusSourceLabel.setObjectName("statusItem")
        self.statusSceneLabel = SmartLabel("场景: --")
        self.statusSceneLabel.setObjectName("statusItem")
        self.statusTimeLabel = SmartLabel()
        self.statusTimeLabel.setObjectName("statusItem")

        statusbar.addWidget(self.statusDot)
        statusbar.addWidget(self.statusSourceLabel)
        statusbar.addWidget(self.statusSceneLabel)
        statusbar.addPermanentWidget(self.statusTimeLabel)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        self.statusTimeLabel.setText(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")

    # ────────────────────────────────────────
    #  日志桥接（兼容 controller 中的 log_edit.append）
    # ────────────────────────────────────────
    class _LogBridge:
        """把 log_edit.append(msg) 转发到 logger + 状态栏"""
        def __init__(self, window):
            self._win = window
        def append(self, msg):
            logger.info(msg)
            # 状态栏显示最新一条（截断）
            short = msg if len(msg) <= 60 else msg[:57] + "..."
            self._win.statusSourceLabel.setText(short)

    # ────────────────────────────────────────
    #  辅助方法
    # ────────────────────────────────────────
    def _load_stylesheet(self):
        try:
            with open("resources/style.qss", "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            logger.warning(f"加载样式表失败: {e}")

    def show_video(self):
        self.placeholderWidget.hide()
        self.label.show()

    def show_placeholder(self):
        self.label.hide()
        self.placeholderWidget.show()

    def set_status_connected(self, source_name: str):
        self.statusDot.setObjectName("statusDotGreen")
        self.statusDot.style().unpolish(self.statusDot)
        self.statusDot.style().polish(self.statusDot)
        self.statusSourceLabel.setText(source_name)

    def set_status_disconnected(self):
        self.statusDot.setObjectName("statusDotRed")
        self.statusDot.style().unpolish(self.statusDot)
        self.statusDot.style().polish(self.statusDot)
        self.statusSourceLabel.setText("未连接")

    def eventFilter(self, obj, event):
        if obj is self.centralWidget() and event.type() == QtCore.QEvent.Type.Resize:
            if hasattr(self, 'particle_bg'):
                self.particle_bg.resize(obj.size())
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        stop_all_servers()
        super().closeEvent(event)


# ── 兼容 QLabel 别名 ──
SmartLabel = QLabel


# ══════════════════════════════════════════════
#  启动
# ══════════════════════════════════════════════
def main():
    logger.setLevel(getattr(logging, "INFO"))
    logger.info(f"🚀 {gradient_text(f'Smart-Client v{__version__} launched!')}")
    logger.info(f"⭐ If you like it, give us a star: {__url__}")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei", 10))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

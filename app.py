import os
import sys
import math
import random
import logging
from datetime import datetime
from PySide6 import QtCore
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QPushButton, QComboBox,
    QTableWidget, QTreeWidget, QToolBar, QHeaderView,
    QAbstractItemView, QSizePolicy, QApplication, QStatusBar,
)

from utils.logger import logger
from utils.general import gradient_text
from engine.manager import engine_manager
from ui.main_controller import MainController
from info import __appname__, __url__, __version__


# ── 自动缩放的 QLabel（完全自绘，不触发布局）──
class ScaledLabel(QLabel):
    """等比缩放显示 pixmap，完全自绘避免布局反馈循环。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._raw_pixmap = None

    def setScaledPixmap(self, pixmap):
        """外部调用此方法设置图片（不触发布局更新）"""
        self._raw_pixmap = pixmap
        self.update()  # 只触发 repaint，不触发 relayout

    def paintEvent(self, event):
        """完全自绘：先画背景，再居中等比缩放绘制 pixmap"""
        painter = QPainter(self)
        # 背景
        painter.fillRect(self.rect(), QColor("#0a0a1a"))
        # 画 pixmap
        if self._raw_pixmap and not self._raw_pixmap.isNull():
            sz = self.size()
            scaled = self._raw_pixmap.scaled(
                sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # 居中绘制
            x = (sz.width() - scaled.width()) // 2
            y = (sz.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        painter.end()


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

    # ── 视频区域（支持 1×1 / 2×2 / 3×3 网格）──
    def _build_video_area(self):
        container = QWidget()
        container.setObjectName("videoContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 网格容器（QGridLayout，动态填充格子）
        self.gridContainer = QWidget()
        self.gridContainer.setObjectName("gridContainer")
        self.gridLayout = QGridLayout(self.gridContainer)
        self.gridLayout.setContentsMargins(4, 4, 4, 4)
        self.gridLayout.setSpacing(4)

        # 格子列表：grid_cells[i] = QLabel
        self.grid_cells = []
        self.grid_size = 1  # 当前网格：1=1×1, 2=2×2, 3=3×3

        # 空状态占位
        self.placeholderWidget = QWidget()
        self.placeholderWidget.setObjectName("placeholderWidget")
        ph_layout = QVBoxLayout(self.placeholderWidget)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_icon = QLabel("📹")
        ph_icon.setObjectName("placeholderIcon")
        ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_title = QLabel("等待接入视频源")
        ph_title.setObjectName("placeholderTitle")
        ph_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_hint = QLabel("点击上方工具栏选择图片、视频或摄像头")
        ph_hint.setObjectName("placeholderHint")
        ph_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        skeleton = QWidget()
        skeleton.setObjectName("skeletonBar")
        skeleton.setFixedSize(240, 6)

        ph_layout.addStretch()
        ph_layout.addWidget(ph_icon)
        ph_layout.addSpacing(16)
        ph_layout.addWidget(ph_title)
        ph_layout.addSpacing(8)
        ph_layout.addWidget(ph_hint)
        ph_layout.addSpacing(24)
        ph_layout.addWidget(skeleton, 0, Qt.AlignmentFlag.AlignCenter)
        ph_layout.addStretch()

        layout.addWidget(self.placeholderWidget)
        layout.addWidget(self.gridContainer)
        self.gridContainer.hide()

        # 一次性创建 9 个格子，后续只切换可见性
        self.grid_cells = []
        self.grid_size = 1
        for i in range(9):
            row, col = divmod(i, 3)
            cell = ScaledLabel()
            cell.setObjectName("gridCell")
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            cell.setStyleSheet("background: #0a0a1a; border: none;")
            self.gridLayout.addWidget(cell, row, col)
            self.grid_cells.append(cell)

        # 默认 1×1 模式
        self.set_grid_mode(1)

        return container

    def set_grid_mode(self, size: int):
        """切换网格模式：1=1×1, 2=2×2, 3=3×3（只改可见性和位置，不重建格子）"""
        self.grid_size = size
        count = size * size

        # 重新设置每个格子的行列位置和可见性
        for i, cell in enumerate(self.grid_cells):
            if i < count:
                row, col = divmod(i, size)
                self.gridLayout.addWidget(cell, row, col)
                cell.show()
                border = "border: none;" if size == 1 else "border: 1px solid #1e1e2e; border-radius: 6px;"
                cell.setStyleSheet(f"background: #0a0a1a; {border}")
            else:
                # 从布局中移除多余格子
                self.gridLayout.removeWidget(cell)
                cell.hide()
                cell.clear()

        # 更新行列拉伸（3x3 全拉伸，其余只拉伸用到的行列）
        for i in range(3):
            self.gridLayout.setColumnStretch(i, 1 if i < size else 0)
            self.gridLayout.setRowStretch(i, 1 if i < size else 0)

    def get_grid_cell(self, index: int):
        """获取指定索引的格子"""
        if 0 <= index < len(self.grid_cells):
            return self.grid_cells[index]
        return None

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

        self.statsCountLabel = QLabel("0")
        self.statsCountLabel.setObjectName("statsValue")
        self.statsAlertLabel = QLabel("0")
        self.statsAlertLabel.setObjectName("statsValue")
        self.statsFpsLabel = QLabel("--")
        self.statsFpsLabel.setObjectName("statsValue")
        self.statsSceneLabel = QLabel("未选择")
        self.statsSceneLabel.setObjectName("statsValue")

        for row, (name, widget) in enumerate([
            ("检测目标", self.statsCountLabel),
            ("今日告警", self.statsAlertLabel),
            ("当前帧率", self.statsFpsLabel),
            ("当前场景", self.statsSceneLabel),
        ]):
            lbl = QLabel(name)
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
        title = QLabel("检测记录")
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
        scene_label = QLabel("  场景: ")
        scene_label.setObjectName("toolbarLabel")
        toolbar.addWidget(scene_label)

        self.sceneBox = QComboBox()
        self.sceneBox.setObjectName("sceneBox")
        self.sceneBox.setMinimumWidth(130)
        toolbar.addWidget(self.sceneBox)

        toolbar.addSeparator()

        # 源操作
        self.tb_act_image = QAction("打开图片", self)
        self.tb_act_video = QAction("打开视频", self)
        self.tb_act_camera = QAction("接入摄像头", self)
        toolbar.addAction(self.tb_act_image)
        toolbar.addAction(self.tb_act_video)
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

        toolbar.addSeparator()

        # 网格模式
        self.tb_grid_1x1 = QAction("1×1", self)
        self.tb_grid_2x2 = QAction("2×2", self)
        self.tb_grid_3x3 = QAction("3×3", self)
        for act in [self.tb_grid_1x1, self.tb_grid_2x2, self.tb_grid_3x3]:
            act.setCheckable(True)
        self.tb_grid_1x1.setChecked(True)
        toolbar.addAction(self.tb_grid_1x1)
        toolbar.addAction(self.tb_grid_2x2)
        toolbar.addAction(self.tb_grid_3x3)

        toolbar.addSeparator()

        # 流标签栏：[＋] [标签1] [标签2] ...
        self.btnAddStream = QPushButton("＋")
        self.btnAddStream.setObjectName("streamAddBtn")
        self.btnAddStream.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnAddStream.setFixedSize(28, 26)
        toolbar.addWidget(self.btnAddStream)

        self.streamTabsWidget = QWidget()
        self.streamTabsLayout = QHBoxLayout(self.streamTabsWidget)
        self.streamTabsLayout.setContentsMargins(0, 0, 0, 0)
        self.streamTabsLayout.setSpacing(4)
        toolbar.addWidget(self.streamTabsWidget)

        self._stream_tabs = {}  # {name: QPushButton}

        # 右侧版本号
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        ver_label = QLabel(f"v{__version__}")
        ver_label.setObjectName("versionLabel")
        toolbar.addWidget(ver_label)

    # ────────────────────────────────────────
    #  状态栏
    # ────────────────────────────────────────
    def _setup_statusbar(self):
        statusbar = QStatusBar()
        statusbar.setObjectName("statusBar")
        self.setStatusBar(statusbar)

        self.statusDot = QLabel("●")
        self.statusDot.setObjectName("statusDotRed")
        self.statusSourceLabel = QLabel("未连接")
        self.statusSourceLabel.setObjectName("statusItem")
        self.statusSceneLabel = QLabel("场景: --")
        self.statusSceneLabel.setObjectName("statusItem")
        self.statusTimeLabel = QLabel()
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
        import sys
        # 兼容打包后和开发环境
        candidates = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "_internal", "resources", "style.qss"))
            candidates.append(os.path.join(exe_dir, "resources", "style.qss"))
        candidates.append(os.path.join(os.path.dirname(__file__), "resources", "style.qss"))

        for path in candidates:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
                return
        logger.warning(f"加载样式表失败: {candidates}")

    # ── 流标签管理 ──
    def add_stream_tab(self, name: str, on_click, on_close):
        """添加一个流标签"""
        container = QWidget()
        container.setObjectName("streamTabContainer")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tab = QPushButton(f" {name} ")
        tab.setObjectName("streamTab")
        tab.setCursor(Qt.CursorShape.PointingHandCursor)
        tab.setFixedHeight(26)
        tab.setCheckable(True)
        tab.clicked.connect(lambda checked, n=name: on_click(n))

        close_btn = QPushButton("✕")
        close_btn.setObjectName("streamTabClose")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFixedSize(20, 26)
        close_btn.clicked.connect(lambda checked, n=name: on_close(n))

        layout.addWidget(tab)
        layout.addWidget(close_btn)
        self.streamTabsLayout.addWidget(container)
        self._stream_tabs[name] = container

    def remove_stream_tab(self, name: str):
        """移除一个流标签"""
        tab = self._stream_tabs.pop(name, None)
        if tab:
            self.streamTabsLayout.removeWidget(tab)
            tab.deleteLater()

    def switch_stream_tab(self, name: str):
        """切换选中状态"""
        for n, container in self._stream_tabs.items():
            tab_btn = container.findChild(QPushButton, "streamTab")
            if tab_btn:
                tab_btn.setChecked(n == name)

    def show_video(self):
        """显示网格，隐藏占位"""
        self.placeholderWidget.hide()
        self.gridContainer.show()

    def show_placeholder(self):
        """显示占位，隐藏网格"""
        self.gridContainer.hide()
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
        if hasattr(self, 'controller'):
            self.controller.cleanup()
        engine_manager.unload()
        super().closeEvent(event)


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

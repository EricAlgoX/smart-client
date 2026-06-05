import sys
import math
import random
import logging
from datetime import datetime
from PySide6 import QtCore
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QSplitter, QGroupBox, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QSlider, QTableWidget,
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
    """可在任意父控件上叠加的漂浮粒子层"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dots = []
        self._init_dots(40)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def _init_dots(self, n):
        for _ in range(n):
            self.dots.append({
                'x': random.uniform(0, 1920), 'y': random.uniform(0, 1080),
                'r': random.uniform(2, 6),
                'vx': random.uniform(-0.3, 0.3), 'vy': random.uniform(-0.2, 0.2),
                'alpha': random.uniform(15, 50),
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
            breathe = d['alpha'] + 10 * (0.5 + 0.5 * math.sin(d['phase']))
            color = QColor.fromHsv(d['hue'], 80, 200, int(breathe))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(d['x']), int(d['y']), int(d['r']), int(d['r']))
        painter.end()


# ══════════════════════════════════════════════════════
#  MainWindow — 工业主界面
# ══════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    """工业级视觉分析主窗口：菜单栏 / 工具栏 / 左导航 / 中视频 / 右结果 / 底日志"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__appname__} v{__version__}")
        self.setMinimumSize(1280, 720)
        self.resize(1600, 900)
        self.setWindowIcon(QIcon("resources/app.ico"))

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._setup_connections()

        # 加载样式表
        self._load_stylesheet()

        # 控制器
        self.controller = MainController(self)

        # 粒子背景（叠在 centralWidget 上）
        self.particle_bg = ParticleBackground(self.centralWidget())
        self.particle_bg.lower()  # 置底
        self.centralWidget().installEventFilter(self)

    # ────────────────────────────────────────────
    #  UI 构建
    # ────────────────────────────────────────────
    def _setup_ui(self):
        """构建主界面布局"""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # ── 主分割器：上(水平分割) + 下(日志) ──
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setHandleWidth(3)

        # ── 水平分割器：左(导航) + 中(视频) + 右(结果) ──
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.setHandleWidth(3)

        h_splitter.addWidget(self._build_left_panel())
        h_splitter.addWidget(self._build_center_panel())
        h_splitter.addWidget(self._build_right_panel())

        h_splitter.setStretchFactor(0, 0)  # 左侧固定
        h_splitter.setStretchFactor(1, 1)  # 中间拉伸
        h_splitter.setStretchFactor(2, 0)  # 右侧固定
        h_splitter.setSizes([280, 800, 360])

        main_splitter.addWidget(h_splitter)
        main_splitter.addWidget(self._build_bottom_panel())
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        main_splitter.setSizes([680, 160])

        main_layout.addWidget(main_splitter)

    # ── 左侧面板：源管理 + 参数 + 操作 ──
    def _build_left_panel(self):
        panel = QWidget()
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── 源管理树 ──
        source_group = QGroupBox("输入源")
        source_group.setObjectName("sourceGroup")
        source_layout = QVBoxLayout(source_group)
        source_layout.setContentsMargins(6, 14, 6, 6)
        source_layout.setSpacing(4)

        self.sourceTree = QTreeWidget()
        self.sourceTree.setHeaderHidden(True)
        self.sourceTree.setObjectName("sourceTree")
        self.sourceTree.setRootIsDecorated(False)
        self.sourceTree.setIndentation(0)
        # 初始占位提示
        root = self.sourceTree.invisibleRootItem()
        hint = QTreeWidgetItem(root, ["  暂无输入源，请通过工具栏添加"])
        hint.setFlags(Qt.ItemFlag.NoItemFlags)
        hint.setForeground(0, QColor("#4a4a65"))

        # 添加源按钮栏
        source_btn_widget = QWidget()
        source_btn_layout = QGridLayout(source_btn_widget)
        source_btn_layout.setContentsMargins(0, 0, 0, 0)
        source_btn_layout.setSpacing(4)

        self.btnAddImage = QPushButton("📷 图片")
        self.btnAddFolder = QPushButton("📁 文件夹")
        self.btnAddVideo = QPushButton("🎬 视频")
        self.btnAddStream = QPushButton("📡 视频流")
        for btn in [self.btnAddImage, self.btnAddFolder, self.btnAddVideo, self.btnAddStream]:
            btn.setObjectName("sourceBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        source_btn_layout.addWidget(self.btnAddImage, 0, 0)
        source_btn_layout.addWidget(self.btnAddFolder, 0, 1)
        source_btn_layout.addWidget(self.btnAddVideo, 1, 0)
        source_btn_layout.addWidget(self.btnAddStream, 1, 1)

        source_layout.addWidget(self.sourceTree)
        source_layout.addWidget(source_btn_widget)
        layout.addWidget(source_group)

        # ── 模型参数区 ──
        param_group = QGroupBox("模型参数")
        param_group.setObjectName("paramGroup")
        param_layout = QGridLayout(param_group)
        param_layout.setContentsMargins(8, 16, 8, 8)
        param_layout.setSpacing(8)
        param_layout.setColumnStretch(1, 1)

        self.selectModelBox = QComboBox()
        self.selectModelBox.setObjectName("selectModelBox")
        param_layout.addWidget(QLabel("算法模型"), 0, 0, 1, 2)
        param_layout.addWidget(self.selectModelBox, 1, 0, 1, 2)

        # NMS
        self.nmsSpinBox = QDoubleSpinBox()
        self.nmsSpinBox.setRange(0, 1)
        self.nmsSpinBox.setSingleStep(0.01)
        self.nmsSpinBox.setValue(0.5)
        self.nmsSlider = QSlider(Qt.Orientation.Horizontal)
        self.nmsSlider.setRange(0, 100)
        self.nmsSlider.setValue(50)
        lbl_nms = QLabel("重叠度 (NMS)")
        lbl_nms.setObjectName("paramLabel")
        param_layout.addWidget(lbl_nms, 2, 0, 1, 2)
        param_layout.addWidget(self.nmsSlider, 3, 0)
        param_layout.addWidget(self.nmsSpinBox, 3, 1)

        # 置信度
        self.conSpinBox = QDoubleSpinBox()
        self.conSpinBox.setRange(0, 1)
        self.conSpinBox.setSingleStep(0.01)
        self.conSpinBox.setValue(0.3)
        self.conSlider = QSlider(Qt.Orientation.Horizontal)
        self.conSlider.setRange(0, 100)
        self.conSlider.setValue(30)
        lbl_con = QLabel("置信度 (CON)")
        lbl_con.setObjectName("paramLabel")
        param_layout.addWidget(lbl_con, 4, 0, 1, 2)
        param_layout.addWidget(self.conSlider, 5, 0)
        param_layout.addWidget(self.conSpinBox, 5, 1)

        # 超时
        self.timeoutSpinBox = QDoubleSpinBox()
        self.timeoutSpinBox.setRange(0, 9999999)
        self.timeoutSpinBox.setValue(3)
        lbl_timeout = QLabel("超时 (min)")
        lbl_timeout.setObjectName("paramLabel")
        param_layout.addWidget(lbl_timeout, 6, 0)
        param_layout.addWidget(self.timeoutSpinBox, 6, 1)

        layout.addWidget(param_group)

        # ── 操作按钮区 ──
        btn_group = QGroupBox("操作")
        btn_group.setObjectName("btnGroup")
        btn_layout = QGridLayout(btn_group)
        btn_layout.setContentsMargins(8, 16, 8, 8)
        btn_layout.setSpacing(6)

        self.startDetectionButton = QPushButton("▶  开始推理")
        self.startDetectionButton.setObjectName("startDetectionButton")
        self.startDetectionButton.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setROIButton = QPushButton("🎯  设置围栏")
        self.setROIButton.setObjectName("secondaryBtn")
        self.clearROIButton = QPushButton("🗑️  清除围栏")
        self.clearROIButton.setObjectName("secondaryBtn")
        self.saveDataButton = QPushButton("💾  保存数据")
        self.saveDataButton.setCheckable(True)
        self.saveDataButton.setObjectName("secondaryBtn")
        self.clearImageButton = QPushButton("🧹  清空画面")
        self.clearImageButton.setObjectName("secondaryBtn")

        for btn in [self.setROIButton, self.clearROIButton, self.saveDataButton, self.clearImageButton]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_layout.addWidget(self.startDetectionButton, 0, 0, 1, 2)
        btn_layout.addWidget(self.setROIButton, 1, 0)
        btn_layout.addWidget(self.clearROIButton, 1, 1)
        btn_layout.addWidget(self.saveDataButton, 2, 0)
        btn_layout.addWidget(self.clearImageButton, 2, 1)

        layout.addWidget(btn_group)
        layout.addStretch()
        return panel

    # ── 中间面板：视频显示 ──
    def _build_center_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # 视频区容器（居中占位 + 视频画面）
        self.videoContainer = QWidget()
        self.videoContainer.setObjectName("videoContainer")
        container_layout = QVBoxLayout(self.videoContainer)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel()
        self.label.setObjectName("videoLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(640, 360)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container_layout.addWidget(self.label)

        # 空状态占位（居中显示）
        self.placeholderWidget = QWidget()
        self.placeholderWidget.setObjectName("placeholderWidget")
        ph_layout = QVBoxLayout(self.placeholderWidget)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ph_icon = QLabel("🎥")
        ph_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_icon.setStyleSheet("font-size: 48px; background: transparent; border: none;")
        ph_title = QLabel("等待输入源")
        ph_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_title.setObjectName("placeholderTitle")
        ph_hint = QLabel("请从左侧导航选择图片、视频或视频流")
        ph_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_hint.setObjectName("placeholderHint")

        ph_layout.addStretch()
        ph_layout.addWidget(ph_icon)
        ph_layout.addSpacing(8)
        ph_layout.addWidget(ph_title)
        ph_layout.addWidget(ph_hint)
        ph_layout.addStretch()

        container_layout.addWidget(self.placeholderWidget)
        self.label.hide()  # 初始隐藏视频，显示占位

        layout.addWidget(self.videoContainer)
        return panel

    # ── 右侧面板：检测结果 + 统计 ──
    def _build_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 检测结果表格
        result_group = QGroupBox("检测结果")
        result_group.setObjectName("resultGroup")
        result_layout = QVBoxLayout(result_group)

        self.tableWidget = QTableWidget(8, 4)
        self.tableWidget.setObjectName("resultTable")
        self.tableWidget.setHorizontalHeaderLabels(["类别", "置信度", "坐标", "图像"])
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tableWidget.setColumnWidth(3, 80)
        self.tableWidget.verticalHeader().setDefaultSectionSize(28)
        self.tableWidget.setAlternatingRowColors(True)
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tableWidget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        result_layout.addWidget(self.tableWidget)

        layout.addWidget(result_group)

        # 统计信息
        stats_group = QGroupBox("统计信息")
        stats_group.setObjectName("statsGroup")
        stats_layout = QGridLayout(stats_group)
        stats_layout.setSpacing(6)

        stats_layout.addWidget(QLabel("检测目标数:"), 0, 0)
        self.statsCountLabel = QLabel("0")
        self.statsCountLabel.setObjectName("statsValue")
        stats_layout.addWidget(self.statsCountLabel, 0, 1)

        stats_layout.addWidget(QLabel("推理耗时:"), 1, 0)
        self.statsTimeLabel = QLabel("-- ms")
        self.statsTimeLabel.setObjectName("statsValue")
        stats_layout.addWidget(self.statsTimeLabel, 1, 1)

        stats_layout.addWidget(QLabel("帧率:"), 2, 0)
        self.statsFpsLabel = QLabel("-- fps")
        self.statsFpsLabel.setObjectName("statsValue")
        stats_layout.addWidget(self.statsFpsLabel, 2, 1)

        layout.addWidget(stats_group)
        layout.addStretch()
        return panel

    # ── 底部面板：日志 ──
    def _build_bottom_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.log_edit = QTextEdit()
        self.log_edit.setObjectName("logEdit")
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(200)
        layout.addWidget(self.log_edit)

        return panel

    # ────────────────────────────────────────────
    #  菜单栏
    # ────────────────────────────────────────────
    def _setup_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setObjectName("menuBar")

        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        act_open_img = QAction("打开图片", self)
        act_open_vid = QAction("打开视频", self)
        act_open_dir = QAction("打开文件夹", self)
        act_open_stream = QAction("打开视频流", self)
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_open_img)
        file_menu.addAction(act_open_vid)
        file_menu.addAction(act_open_dir)
        file_menu.addAction(act_open_stream)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        # 保存这些 action 引用供 controller 绑定
        self.act_open_img = act_open_img
        self.act_open_vid = act_open_vid
        self.act_open_dir = act_open_dir
        self.act_open_stream = act_open_stream

        # 模型菜单
        model_menu = menu_bar.addMenu("模型")

        # 视图菜单
        view_menu = menu_bar.addMenu("视图")

        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")
        act_about = QAction("关于", self)
        act_about.triggered.connect(lambda: QMessageBox.about(
            self, "关于",
            f"<h3>{__appname__} v{__version__}</h3>"
            f"<p>AI 视觉智能分析客户端</p>"
            f"<p>作者: EricReno<br>邮箱: christopher0527@163.com</p>"
            f"<p>仓库: <a href='{__url__}'>{__url__}</a></p>"
        ))
        help_menu.addAction(act_about)

    # ────────────────────────────────────────────
    #  工具栏
    # ────────────────────────────────────────────
    def _setup_toolbar(self):
        toolbar = QToolBar("快捷操作")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        self.tb_act_start = QAction("▶  开始推理", self)
        self.tb_act_stop = QAction("⏹  停止", self)

        toolbar.addAction(self.tb_act_start)
        toolbar.addAction(self.tb_act_stop)
        toolbar.addSeparator()

        # 右侧 spacer + 版本号
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        ver_label = QLabel(f"v{__version__}")
        ver_label.setObjectName("versionLabel")
        toolbar.addWidget(ver_label)

    # ────────────────────────────────────────────
    #  状态栏
    # ────────────────────────────────────────────
    def _setup_statusbar(self):
        statusbar = QStatusBar()
        statusbar.setObjectName("statusBar")
        self.setStatusBar(statusbar)

        # 连接指示灯
        self.statusDot = QLabel("●")
        self.statusDot.setObjectName("statusDotRed")
        self.statusSourceLabel = QLabel("未连接")
        self.statusSourceLabel.setObjectName("statusItem")
        self.statusModelLabel = QLabel("模型: --")
        self.statusModelLabel.setObjectName("statusItem")
        self.statusTimeLabel = QLabel()
        self.statusTimeLabel.setObjectName("statusItem")

        statusbar.addWidget(self.statusDot)
        statusbar.addWidget(self.statusSourceLabel)
        statusbar.addWidget(self.statusModelLabel)
        statusbar.addPermanentWidget(self.statusTimeLabel)

        # 时钟定时器
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        self.statusTimeLabel.setText(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")

    # ────────────────────────────────────────────
    #  信号绑定
    # ────────────────────────────────────────────
    def _setup_connections(self):
        """菜单栏和工具栏的信号由 controller 绑定，此处为空"""
        pass

    def show_video(self):
        """从占位状态切换到视频显示"""
        self.placeholderWidget.hide()
        self.label.show()

    def show_placeholder(self):
        """从视频切换回占位状态"""
        self.label.hide()
        self.placeholderWidget.show()

    def set_status_connected(self, source_name: str):
        """状态栏：已连接"""
        self.statusDot.setObjectName("statusDotGreen")
        self.statusDot.style().unpolish(self.statusDot)
        self.statusDot.style().polish(self.statusDot)
        self.statusSourceLabel.setText(source_name)

    def set_status_disconnected(self):
        """状态栏：未连接"""
        self.statusDot.setObjectName("statusDotRed")
        self.statusDot.style().unpolish(self.statusDot)
        self.statusDot.style().polish(self.statusDot)
        self.statusSourceLabel.setText("未连接")

    # ────────────────────────────────────────────
    #  辅助
    # ────────────────────────────────────────────
    def _load_stylesheet(self):
        try:
            with open("resources/style.qss", "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            logger.warning(f"加载样式表失败: {e}")

    def eventFilter(self, obj, event):
        """让粒子背景跟随 centralWidget 大小"""
        if obj is self.centralWidget() and event.type() == QtCore.QEvent.Type.Resize:
            if hasattr(self, 'particle_bg'):
                self.particle_bg.resize(obj.size())
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        stop_all_servers()
        super().closeEvent(event)


# ══════════════════════════════════════════════════════
#  启动
# ══════════════════════════════════════════════════════
def main():
    logger.setLevel(getattr(logging, "INFO"))
    logger.info(f"🚀 {gradient_text(f'Smart-Client v{__version__} launched!')}")
    logger.info(f"⭐ If you like it, give us a star: {__url__}")

    # 高 DPI 适配
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

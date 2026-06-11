import os
import json
import csv
from datetime import datetime
from PySide6.QtWidgets import QTableWidgetItem, QMessageBox, QTreeWidgetItem, QFileDialog, QMenu
from PySide6.QtGui import QPixmap
from core.stream_session import StreamSession
from core.stream_manager import StreamManager
from engine.manager import engine_manager
from utils.logger import logger
from utils.profiler import profiler
from core.stream import select_image, select_video, select_stream
from ui.settings_dialog import SettingsDialog


class MainController:
    """多流控制器：场景切换 / 流管理 / 告警 / 记录"""

    def __init__(self, window):
        self.window = window
        self.ui = window
        self.current_scene = None
        self.alert_count = 0

        # 多流管理
        self.stream_manager = StreamManager()
        self._workers = []  # 持有 worker 引用，防止 GC

        # 默认参数
        self._nms = 0.5
        self._confidence = 0.3
        self._timeout = 3

        # 加载场景
        self._load_scenes()
        self._setup_connections()

        # 默认加载第一个场景
        if self.ui.sceneBox.count() > 0:
            self._on_scene_changed(0)

    # ────────────────────────────────────────
    #  路径查找（兼容打包后和开发环境）
    # ────────────────────────────────────────
    @staticmethod
    def _find_file(relative_path: str) -> str:
        import sys
        candidates = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "_internal", relative_path))
            candidates.append(os.path.join(exe_dir, relative_path))
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), relative_path))
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[-1]

    # ────────────────────────────────────────
    #  初始化
    # ────────────────────────────────────────
    def _load_scenes(self):
        try:
            config_path = self._find_file("scenes.json")
            with open(config_path, "r", encoding="utf-8") as f:
                self.scenes = json.load(f)
            for key, scene in self.scenes.items():
                self.ui.sceneBox.addItem(f"{scene['icon']}  {scene['name']}", key)
        except Exception as e:
            logger.error(f"加载场景配置失败: {e}")
            self.scenes = {}

    def _setup_connections(self):
        ui = self.ui

        # 工具栏
        ui.tb_act_image.triggered.connect(lambda: self.select_source("image"))
        ui.tb_act_video.triggered.connect(lambda: self.select_source("video"))
        ui.tb_act_camera.triggered.connect(lambda: self.select_source("camera"))
        ui.tb_act_start.triggered.connect(self.startDetection)
        ui.tb_act_stop.triggered.connect(self._stop_detection)
        ui.tb_act_settings.triggered.connect(self._open_settings)

        # 场景切换
        ui.sceneBox.currentIndexChanged.connect(self._on_scene_changed)

        # 流标签栏
        ui.btnAddStream.clicked.connect(self._show_add_stream_menu)

        # 导出记录
        ui.btnExportRecords.clicked.connect(self._export_records)

    # ────────────────────────────────────────
    #  场景切换
    # ────────────────────────────────────────
    def _on_scene_changed(self, index):
        scene_key = self.ui.sceneBox.currentData()
        if not scene_key or scene_key not in self.scenes:
            return

        self.current_scene = self.scenes[scene_key]
        scene_name = self.current_scene['name']

        success = engine_manager.load_scene(scene_key)
        if success:
            self.ui.log_edit.append(f"已切换场景: {scene_name}")
        else:
            self.ui.log_edit.append(f"❌ 场景切换失败: {scene_name}")

        self.ui.statusSceneLabel.setText(f"场景: {scene_name}")
        self.ui.statsSceneLabel.setText(scene_name)

    # ────────────────────────────────────────
    #  ＋ 按钮：弹出菜单选择源类型
    # ────────────────────────────────────────
    def _show_add_stream_menu(self):
        menu = QMenu(self.window)
        act_img = menu.addAction("📷  打开图片")
        act_vid = menu.addAction("🎬  打开视频")
        act_cam = menu.addAction("📡  接入摄像头")

        action = menu.exec(self.ui.btnAddStream.mapToGlobal(
            self.ui.btnAddStream.rect().bottomLeft()
        ))

        if action == act_img:
            self.select_source("image")
        elif action == act_vid:
            self.select_source("video")
        elif action == act_cam:
            self.select_source("camera")

    # ────────────────────────────────────────
    #  源选择 → 创建 StreamSession
    # ────────────────────────────────────────
    def select_source(self, source_type):
        # 提前检查上限
        if len(self.stream_manager.get_all_names()) >= 9:
            QMessageBox.warning(self.window, "提示", "最多支持 9 路视频流")
            return

        if source_type == "image":
            result = select_image(self)
        elif source_type == "video":
            result = select_video(self)
        elif source_type == "camera":
            result = select_stream(self)
        else:
            return

        # 异步连接（摄像头/视频流）
        if result and 'worker' in result:
            # 防止重复连接
            if hasattr(self, '_connect_worker') and self._connect_worker is not None:
                if self._connect_worker.isRunning():
                    logger.warning("[Controller] 已有连接进行中，跳过")
                    return
                self._connect_worker = None

            worker = result['worker']
            self._connect_worker = worker
            source_name = result['stream_name']
            self.ui.log_edit.append(f"正在连接: {source_name} ...")
            # 在第一个格子显示连接状态
            cell = self.ui.get_grid_cell(0)
            if cell:
                cell.setText("⏳ 正在连接...")
                cell.setStyleSheet("color: #60a5fa; font-size: 16px; background: #0a0a1a; border: 1px solid #1e1e2e; border-radius: 6px;")
            worker.finished.connect(
                lambda stream, frame, fname: self._on_stream_connected(stream, frame, fname, source_name))
            worker.error.connect(self._on_stream_error)
            worker.start()
            logger.info(f"[Controller] worker 已启动")
            return

        # 同步结果（图片/视频）
        if result and 'frame' in result:
            self._create_session(result, source_type)
        elif result is None:
            pass
        else:
            QMessageBox.critical(self.window, "错误", "无法加载输入源")

    def _on_stream_connected(self, stream, frame, frame_name, source_name):
        """摄像头连接成功"""
        result = {
            'stream': stream,
            'stream_name': source_name,
            'frame': frame,
            'frame_name': frame_name,
        }
        self._create_session(result, "camera")

    def _on_stream_error(self, error_msg):
        cell = self.ui.get_grid_cell(0)
        if cell:
            cell.setText("❌ 连接失败")
            cell.setStyleSheet("color: #ef4444; font-size: 14px; background: #0a0a1a; border: 1px solid #1e1e2e; border-radius: 6px;")
        self.ui.log_edit.append(f"❌ 连接失败: {error_msg}")
        QMessageBox.critical(self.window, "连接失败", error_msg)

    def _create_session(self, source, source_type):
        """创建 StreamSession 并添加到管理器"""
        name = str(source['stream_name'])

        # 检查是否已满（最多 9 路）
        current_count = len(self.stream_manager.get_all_names())
        if current_count >= 9:
            QMessageBox.warning(self.window, "提示", "最多支持 9 路视频流")
            # 恢复 UI 状态（清除"正在连接中"的提示）
            self._refresh_grid()
            self.ui.show_video()
            return

        # 先计算目标网格并更新 max_slots（必须在 add 之前！）
        new_count = current_count + 1
        if new_count == 1:
            target_grid = 1
        elif new_count <= 4:
            target_grid = 2
        else:
            target_grid = 3

        if target_grid != self.ui.grid_size:
            self._set_grid_mode(target_grid)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
        else:
            # 即使不切网格，也要更新 max_slots
            self.stream_manager.max_slots = target_grid * target_grid

        session = StreamSession(
            name=name,
            video_stream=source['stream'],
            first_frame=source['frame'],
            frame_name=source['frame_name'],
            source_type=source_type,
        )

        # 注册到管理器（此时 max_slots 已正确）
        session_name = self.stream_manager.add(session)

        # 连接所有 session 到格子
        self._refresh_grid()
        self.ui.show_video()

        # 添加 UI 标签
        self.ui.add_stream_tab(
            session_name,
            on_click=self._on_tab_clicked,
            on_close=self._on_tab_close,
        )

        # 标记为当前标签
        self.ui.switch_stream_tab(session_name)
        self.ui.set_status_connected(session_name)
        self.stream_manager._active_name = session_name

        # 启动推理
        if engine_manager.is_loaded:
            session.start_inference(confidence=self._confidence, nms=self._nms)
            self.ui.log_edit.append(f"✅ {session_name} 已连接，推理已启动")
        else:
            self.ui.log_edit.append(f"✅ {session_name} 已连接，请选择场景后开始推理")

        # 视频/摄像头自动开始
        if source_type in ("video", "camera"):
            session.start_streaming()

    # ────────────────────────────────────────
    #  网格模式
    # ────────────────────────────────────────
    def _set_grid_mode(self, size: int):
        """切换网格模式 1×1 / 2×2 / 3×3（格子不再重建，只改可见性）"""
        self.stream_manager.max_slots = size * size
        self.ui.set_grid_mode(size)
        self.ui.show_video()
        # 注意：不在这里调 _refresh_grid，由调用方决定何时连接 session

    def _refresh_grid(self):
        """刷新所有格子的显示（按 slot 索引对齐）"""
        cells = self.ui.grid_cells
        visible_count = self.ui.grid_size * self.ui.grid_size
        border = "border: none;" if self.ui.grid_size == 1 else "border: 1px solid #1e1e2e; border-radius: 6px;"

        for i, cell in enumerate(cells):
            if i >= visible_count:
                break
            session = self.stream_manager.get_slot_session(i)
            if session:
                if session.converter is None:
                    self._connect_session_to_cell(session, cell)
            else:
                cell.clear()
                cell.setText("")
                cell.setStyleSheet(f"background: #0a0a1a; {border}")

    def _connect_session_to_cell(self, session, cell_label):
        """把 session 的 converter 输出连接到指定格子"""
        if session.converter is not None:
            session.converter.stop()

        # 强制更新布局，确保格子有正确的尺寸
        cell_label.show()
        cell_label.updateGeometry()

        def on_cell_frame(qimg, details, _path='', _original_rgb=None):
            pixmap = QPixmap.fromImage(qimg)
            cell_label.setScaledPixmap(pixmap)
            if details:
                self._process_alerts(details, session)
                self._update_records(details, session)
                self._update_stats(details, session)

        session.activate_grid(on_cell_frame, lambda: cell_label.size())

        # 只在还没运行时才启动 reader（避免重复创建线程导致同源流冲突）
        if not session.running and session.source_type in ("video", "camera"):
            session.start_streaming()
        elif session.source_type == "image":
            session.frame_queue.put((session.first_frame, session.frame_name))

    # ────────────────────────────────────────
    #  流标签操作
    # ────────────────────────────────────────
    def _on_tab_clicked(self, name):
        """点击标签切换"""
        self._switch_to_session(name)

    def _on_tab_close(self, name: str):
        """关闭标签（只清理被删的流，不动其他流）"""
        if not name:
            return

        # 先停 converter（避免信号指向即将删除的格子）
        session = self.stream_manager.get(name)
        if session and session.converter is not None:
            session.converter.stop()
            session.converter = None

        # 清除对应格子内容
        slot_idx = self.stream_manager.slots.index(name) if name in self.stream_manager.slots else -1
        if slot_idx >= 0:
            cell = self.ui.get_grid_cell(slot_idx)
            if cell:
                cell.setScaledPixmap(None)
                cell.setText("")
                border = "border: none;" if self.ui.grid_size == 1 else "border: 1px solid #1e1e2e; border-radius: 6px;"
                cell.setStyleSheet(f"background: #0a0a1a; {border}")

        # 从管理器移除（内部会调 cleanup 停 reader 和 inference）
        self.stream_manager.remove(name)
        self.ui.remove_stream_tab(name)
        self.ui.log_edit.append(f"已关闭: {name}")

        # 剩余流前移填充空位（只重连位置变了的流）
        self._compact_grid()

    def _compact_grid(self):
        """把剩余流紧凑排列到格子中（只重连位置变了的流）"""
        cells = self.ui.grid_cells
        border = "border: none;" if self.ui.grid_size == 1 else "border: 1px solid #1e1e2e; border-radius: 6px;"

        # 记录每个 session 当前所在的 slot
        old_slot_map = {}
        for i in range(self.stream_manager.max_slots):
            name = self.stream_manager.slots[i]
            if name:
                old_slot_map[name] = i

        # 按 slot 顺序收集剩余 session
        active_sessions = []
        for i in range(self.stream_manager.max_slots):
            session = self.stream_manager.get_slot_session(i)
            if session:
                active_sessions.append(session)

        # 确定合适的网格大小
        count = len(active_sessions)
        if count == 0:
            self.ui.show_placeholder()
            self.ui.set_status_disconnected()
            return
        elif count <= 4:
            target_grid = 2
        else:
            target_grid = 3

        # 如果需要降级网格
        if target_grid != self.ui.grid_size:
            self._set_grid_mode(target_grid)
            cells = self.ui.grid_cells
            border = "border: none;" if target_grid == 1 else "border: 1px solid #1e1e2e; border-radius: 6px;"

        visible_count = self.ui.grid_size * self.ui.grid_size

        # 重新分配到连续格子
        for i in range(visible_count):
            cell = cells[i]
            if i < count:
                session = active_sessions[i]
                old_idx = old_slot_map.get(session.name, -1)
                self.stream_manager.slots[i] = session.name

                if old_idx == i:
                    # 位置没变，不动
                    pass
                else:
                    # 位置变了，重连到新格子
                    if session.converter is not None:
                        session.converter.stop()
                        session.converter = None
                    self._connect_session_to_cell(session, cell)
            else:
                self.stream_manager.slots[i] = None
                cell.setScaledPixmap(None)
                cell.setText("")
                cell.setStyleSheet(f"background: #0a0a1a; {border}")

    def _switch_to_session(self, name):
        """切换 active session（宫格模式下只切引用，不动 converter）"""
        # 宫格模式：只更新 active 引用，不动 converter
        old_active = self.stream_manager.get_active()
        if old_active:
            old_active.set_active(False)

        self.stream_manager._active_name = name
        session = self.stream_manager.get_active()
        if session:
            session.set_active(True)

        self.ui.switch_stream_tab(name)
        self.ui.set_status_connected(name)
        if session:
            self._refresh_alerts(session)
            self._refresh_records(session)

    # ────────────────────────────────────────
    #  推理控制（操作 active session）
    # ────────────────────────────────────────
    def startDetection(self):
        session = self.stream_manager.get_active()
        if session is None:
            self.ui.log_edit.append("请先接入视频源")
            return
        if not engine_manager.is_loaded:
            self.ui.log_edit.append("请先选择检测场景")
            return

        if session.source_type == "image":
            session.frame_queue.put((session.first_frame, session.frame_name))
            return

        if not session.running:
            session.start_streaming()
            if session.inference_worker is None:
                session.start_inference(self._confidence, self._nms)
        else:
            session.stop_inference()

    def _stop_detection(self):
        session = self.stream_manager.get_active()
        if session:
            session.stop_inference()
            self.ui.log_edit.append(f"检测已停止: {session.name}")

    # ────────────────────────────────────────
    #  显示回调（active session 的 converter 触发）
    # ────────────────────────────────────────
    @profiler.measure("display")
    def display(self, qimg, details=[], path='', original_rgb=None):
        if original_rgb is not None:
            self.current_display_image = original_rgb

        qpix = QPixmap.fromImage(qimg)
        # 显示到 active session 对应的格子
        session = self.stream_manager.get_active()
        if session:
            slot_idx = self.stream_manager.slots.index(session.name) if session.name in self.stream_manager.slots else -1
            if slot_idx >= 0:
                cell = self.ui.get_grid_cell(slot_idx)
                if cell:
                    cell.setScaledPixmap(qpix)

        if details and session:
            if session:
                self._process_alerts(details, session)
                self._update_records(details, session)
                self._update_stats(details, session)

    def _process_alerts(self, details, session):
        scene_key = self.ui.sceneBox.currentData()
        scene = self.scenes.get(scene_key, {})
        alert_rules = scene.get('alert_rules', {})

        for det in details:
            class_name = det.get('class', '')
            score = float(det.get('score', 0))
            ocr_text = det.get('text', '')
            level = alert_rules.get(class_name, 'info')
            if score < self._confidence:
                continue

            level_map = {
                'critical': ('🔴', '严重'), 'alert': ('🟠', '告警'),
                'warning': ('🟡', '注意'), 'info': ('🟢', '信息'),
            }
            icon, level_text = level_map.get(level, ('⚪', '信息'))
            detail_text = ocr_text if ocr_text else f"{class_name} ({score:.0%})"
            now = datetime.now().strftime("%H:%M:%S")

            item = QTreeWidgetItem([now, f"{icon} {level_text}", detail_text])
            self.ui.alertList.insertTopLevelItem(0, item)
            if self.ui.alertList.topLevelItemCount() > 100:
                self.ui.alertList.takeTopLevelItem(100)

            if level in ('critical', 'alert'):
                session.alert_count = getattr(session, 'alert_count', 0) + 1
                self.alert_count += 1

    def _update_records(self, details, session):
        now = datetime.now().strftime("%H:%M:%S")
        scene_name = self.current_scene['name'] if self.current_scene else '--'

        for det in details:
            class_name = det.get('class', '')
            score = float(det.get('score', 0))
            ocr_text = det.get('text', '')
            if score < self._confidence:
                continue

            detail_text = ocr_text if ocr_text else f"{score:.0%}"
            row = self.ui.recordTable.rowCount()
            self.ui.recordTable.insertRow(row)
            self.ui.recordTable.setItem(row, 0, QTableWidgetItem(now))
            self.ui.recordTable.setItem(row, 1, QTableWidgetItem(scene_name))
            self.ui.recordTable.setItem(row, 2, QTableWidgetItem(class_name))
            self.ui.recordTable.setItem(row, 3, QTableWidgetItem(detail_text))
            self.ui.recordTable.setItem(row, 4, QTableWidgetItem("📷"))

            session.records.append({
                'time': now, 'scene': scene_name,
                'type': class_name, 'detail': detail_text,
            })

            if self.ui.recordTable.rowCount() > 500:
                self.ui.recordTable.removeRow(0)

    def _update_stats(self, details, session):
        count = len([d for d in details if float(d.get('score', 0)) >= self._confidence])
        total = int(self.ui.statsCountLabel.text() or 0) + count
        self.ui.statsCountLabel.setText(str(total))
        self.ui.statsAlertLabel.setText(str(self.alert_count))

    def _refresh_alerts(self, session):
        """切换 session 时刷新告警区（当前简化：清空）"""
        self.ui.alertList.clear()

    def _refresh_records(self, session):
        """切换 session 时刷新记录表"""
        self.ui.recordTable.setRowCount(0)
        for rec in session.records:
            row = self.ui.recordTable.rowCount()
            self.ui.recordTable.insertRow(row)
            self.ui.recordTable.setItem(row, 0, QTableWidgetItem(rec['time']))
            self.ui.recordTable.setItem(row, 1, QTableWidgetItem(rec['scene']))
            self.ui.recordTable.setItem(row, 2, QTableWidgetItem(rec['type']))
            self.ui.recordTable.setItem(row, 3, QTableWidgetItem(rec['detail']))
            self.ui.recordTable.setItem(row, 4, QTableWidgetItem("📷"))

    def _get_label_size(self):
        try:
            cell = self.ui.get_grid_cell(0)
            return cell.size() if cell else None
        except Exception:
            return None

    # ────────────────────────────────────────
    #  设置
    # ────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(
            self.window, nms=self._nms,
            confidence=self._confidence, timeout=self._timeout,
        )
        if dlg.exec():
            self._nms = dlg.nmsSpin.value()
            self._confidence = dlg.conSpin.value()
            self._timeout = dlg.timeoutSpin.value()
            # 更新当前 active session 的参数
            session = self.stream_manager.get_active()
            if session and session.inference_worker:
                session.inference_worker.confidence = self._confidence
                session.inference_worker.nms = self._nms
            self.ui.log_edit.append(
                f"设置已更新: NMS={self._nms:.2f}, 置信度={self._confidence:.2f}"
            )

    # ────────────────────────────────────────
    #  导出
    # ────────────────────────────────────────
    def _export_records(self):
        session = self.stream_manager.get_active()
        records = session.records if session else []
        if not records:
            QMessageBox.information(self.window, "提示", "暂无检测记录可导出")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self.window, "导出记录",
            f"detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV 文件 (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['time', 'scene', 'type', 'detail'])
                writer.writeheader()
                writer.writerows(records)
            self.ui.log_edit.append(f"✅ 记录已导出: {file_path}")
        except Exception as e:
            self.ui.log_edit.append(f"❌ 导出失败: {e}")

    def cleanup(self):
        self.stream_manager.cleanup_all()
        engine_manager.unload()

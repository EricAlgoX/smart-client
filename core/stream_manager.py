"""管理多个 StreamSession 的生命周期 + 格子分配"""

from typing import Dict, Optional, List, Callable
from core.stream_session import StreamSession
from utils.logger import logger


class StreamManager:
    """管理所有视频流 Session + Grid 格子分配"""

    def __init__(self, max_slots: int = 9):
        self._sessions: Dict[str, StreamSession] = {}
        self._active_name: Optional[str] = None
        self._counter = 0
        self.max_slots = max_slots

        # Grid 格子：slots[i] = session_name 或 None
        self.slots: List[Optional[str]] = [None] * max_slots

    # ── Session 管理 ──

    def add(self, session: StreamSession) -> str:
        """添加 session，自动分配格子"""
        self._counter += 1
        if not session.name:
            session.name = f"流{self._counter}"
        base_name = session.name
        counter = 1
        while session.name in self._sessions:
            session.name = f"{base_name}_{counter}"
            counter += 1

        self._sessions[session.name] = session
        self._assign_slot(session.name)
        logger.info(f"[StreamManager] 添加: {session.name}, 总数: {len(self._sessions)}")
        return session.name

    def remove(self, name: str):
        """移除并清理 session"""
        session = self._sessions.pop(name, None)
        if session:
            session.cleanup()
        self._release_slot(name)

        if self._active_name == name:
            self._active_name = next(iter(self._sessions), None)

        logger.info(f"[StreamManager] 移除: {name}, 剩余: {len(self._sessions)}")

    def switch_to(self, name: str, display_callback, get_label_size):
        """切换 active session（单画面模式）"""
        if name not in self._sessions:
            return

        # 停用旧的
        old = self.get_active()
        if old:
            old.deactivate()

        self._active_name = name
        session = self._sessions[name]
        session.activate(display_callback, get_label_size)

    def get_active(self) -> Optional[StreamSession]:
        if self._active_name and self._active_name in self._sessions:
            return self._sessions[self._active_name]
        return None

    def get(self, name: str) -> Optional[StreamSession]:
        return self._sessions.get(name)

    def get_all_names(self) -> List[str]:
        return list(self._sessions.keys())

    def get_active_name(self) -> Optional[str]:
        return self._active_name

    # ── 格子分配 ──

    def _assign_slot(self, name: str) -> int:
        """分配一个空格子，返回格子索引。满了返回 -1"""
        for i in range(self.max_slots):
            if self.slots[i] is None:
                self.slots[i] = name
                return i
        return -1  # 没有空格子

    def _release_slot(self, name: str):
        """释放格子"""
        for i in range(self.max_slots):
            if self.slots[i] == name:
                self.slots[i] = None

    def get_slot_session(self, slot_index: int) -> Optional[StreamSession]:
        """获取指定格子的 session"""
        if 0 <= slot_index < self.max_slots:
            name = self.slots[slot_index]
            if name:
                return self._sessions.get(name)
        return None

    def get_slot_sessions(self, grid_size: int) -> List[Optional[StreamSession]]:
        """获取当前网格中所有格子的 session"""
        count = grid_size * grid_size
        result = []
        for i in range(count):
            result.append(self.get_slot_session(i))
        return result

    def activate_grid_mode(self, grid_size: int, display_callbacks: List, get_label_size):
        """Grid 模式：激活所有格子中的 session"""
        count = grid_size * grid_size
        for i in range(count):
            session = self.get_slot_session(i)
            if session and i < len(display_callbacks):
                session.activate_grid(display_callbacks[i], get_label_size)

    def activate_single_mode(self, name: str, display_callback, get_label_size):
        """单画面模式：只激活选中的 session"""
        # 停用所有
        for session in self._sessions.values():
            session.deactivate()

        # 激活选中的
        if name in self._sessions:
            self._active_name = name
            self._sessions[name].activate(display_callback, get_label_size)

    def cleanup_all(self):
        """清理所有 session"""
        for session in self._sessions.values():
            session.cleanup()
        self._sessions.clear()
        self._active_name = None
        self.slots = [None] * self.max_slots
        logger.info("[StreamManager] 已清理全部")

"""管理多个 StreamSession 的生命周期"""

from typing import Dict, Optional, List
from core.stream_session import StreamSession
from utils.logger import logger


class StreamManager:
    """管理所有视频流 Session"""

    def __init__(self):
        self._sessions: Dict[str, StreamSession] = {}
        self._active_name: Optional[str] = None
        self._counter = 0

    def add(self, session: StreamSession) -> str:
        """添加 session，返回唯一名称"""
        self._counter += 1
        # 如果没有指定名称，自动生成
        if not session.name:
            session.name = f"流{self._counter}"
        # 重名处理
        base_name = session.name
        counter = 1
        while session.name in self._sessions:
            session.name = f"{base_name}_{counter}"
            counter += 1

        self._sessions[session.name] = session
        logger.info(f"[StreamManager] 添加: {session.name}, 总数: {len(self._sessions)}")
        return session.name

    def remove(self, name: str):
        """移除并清理 session"""
        session = self._sessions.pop(name, None)
        if session:
            session.cleanup()
            logger.info(f"[StreamManager] 移除: {name}, 剩余: {len(self._sessions)}")

        # 如果移除的是 active，切换到其他
        if self._active_name == name:
            self._active_name = next(iter(self._sessions), None)

    def switch_to(self, name: str, display_callback, get_label_size):
        """切换 active session"""
        if name not in self._sessions:
            logger.warning(f"[StreamManager] session 不存在: {name}")
            return

        # 停用旧的
        old = self.get_active()
        if old:
            old.deactivate()

        # 激活新的
        self._active_name = name
        session = self._sessions[name]
        session.activate(display_callback, get_label_size)
        logger.info(f"[StreamManager] 切换到: {name}")

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

    def cleanup_all(self):
        """清理所有 session"""
        for session in self._sessions.values():
            session.cleanup()
        self._sessions.clear()
        self._active_name = None
        logger.info("[StreamManager] 已清理全部")

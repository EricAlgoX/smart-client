from utils.logger import logger

import os
import sys
import subprocess
import threading
from utils.logger import logger
from typing import Dict, Optional

# 维护已启动的算法进程句柄（按算法键名存储）
_RUNNING_PROCESSES: Dict[str, subprocess.Popen] = {}

def _stream_pipe(pipe, log_func, prefix: str) -> None:
    for line in iter(pipe.readline, ""):
        text = line.rstrip("\n\r")
        if text:
            log_func(f"{prefix} {text}")
    pipe.close()

def start_server(algorithms_name: str) -> bool:
    """启动指定算法的 FastAPI 服务。
    - 若已在运行则返回 True。
    - 启动失败返回 False。
    """
    if algorithms_name in _RUNNING_PROCESSES and _RUNNING_PROCESSES[algorithms_name].poll() is None:
        # 已在运行
        logger.info(f"正在运行 SV{algorithms_id}/{script_name} ... (PID: {proc.pid})")
        return True

    algorithms_id = algorithms_name.split('_')[0]

    root_path = '\\'.join(os.path.dirname(__file__).split('\\')[:-2])
    algorithms_path = os.path.join(f'{root_path}\\smartvision', 'algorithms')

    # 遍历 base_dir 下的所有文件夹，找到名字包含 ID 的那个
    target_folder: Optional[str] = None
    for name in os.listdir(algorithms_path):
        if os.path.isdir(os.path.join(algorithms_path, name)) and name.startswith(f"SV{algorithms_id}_"):
            target_folder = os.path.join(algorithms_path, name)
            break

    if not target_folder:
        logger.warning(f"未找到 ID 为 {algorithms_id} 的文件夹")
        return False

    script_name = "run_fastapi.py"
    script_path = os.path.join(target_folder, script_name)
    if not os.path.exists(script_path):
        logger.warning(f"SV{algorithms_id}*/{script_name} 不存在")
        return False

    # 通过 Popen 启动并保存句柄；传入父进程 PID 以便子进程可自行感知父进程退出
    env = os.environ.copy()
    env["PARENT_PID"] = str(os.getpid())

    # 在目标目录作为工作目录启动
    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=target_folder,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        _RUNNING_PROCESSES[algorithms_name] = proc
        t_out = threading.Thread(
            target=_stream_pipe,
            args=(proc.stdout, logger.info, f"[{algorithms_name}]"),
            daemon=True,
        )
        t_out.start()

        logger.info(f"启动 SV{algorithms_id}/{script_name} ... (PID: {proc.pid}) 成功")
        return True
    except Exception as e:
        logger.info(f"启动 SV{algorithms_id}/{script_name} 失败: {e}")
        return False


def stop_server(algorithms_name: str) -> bool:
    """停止指定算法服务。不存在或已退出视为成功。"""
    proc = _RUNNING_PROCESSES.get(algorithms_name)
    if not proc:
        return True

    if proc.poll() is not None:
        # 已退出
        _RUNNING_PROCESSES.pop(algorithms_name, None)
        return True

    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    finally:
        _RUNNING_PROCESSES.pop(algorithms_name, None)
    return True

def stop_all_servers() -> None:
    """停止所有已启动的算法服务。"""
    for name in list(_RUNNING_PROCESSES.keys()):
        try:
            stop_server(name)
            logger.info(f'killed {name}')
        except Exception as e:
            logger.error(e)
            pass

if __name__ == "__main__":
    start_server('01_overflow')
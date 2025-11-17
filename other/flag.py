import queue
import threading

global stop_event

# 设置一个全局事件标志，用于停止线程
stop_event = threading.Event()

# 用一个队列来传递终止信号
exit_queue = queue.Queue()

def signal_handler(sig, frame):
    print("Ctrl+C detected, stopping threads...")
    stop_event.set()  # 设置 stop_event 来停止所有线程
    exit_queue.put("stop")  # 通过队列通知主线程c

class ProcessingStatus:
    def __init__(self):
        self.processing_macs = set()  # 存储正在处理的 mac_id
        self.failed_macs = set()      # 存储失败的 mac_id
        self.lock = threading.Lock()  # 用于线程安全的锁

    def add_processing(self, mac_id):
        with self.lock:
            self.processing_macs.add(mac_id)

    def remove_processing(self, mac_id):
        with self.lock:
            if mac_id in self.processing_macs:
                self.processing_macs.remove(mac_id)

    def add_failed(self, mac_id):
        with self.lock:
            self.failed_macs.add(mac_id)

    def remove_failed(self, mac_id):
        with self.lock:
            if mac_id in self.failed_macs:
                self.failed_macs.remove(mac_id)

    def get_processing(self):
        with self.lock:
            return list(self.processing_macs)

    def get_failed(self):
        with self.lock:
            return list(self.failed_macs)
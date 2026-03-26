import time
import functools
from utils.logger import logger

class PerformanceProfiler:
    """性能分析工具"""

    def __init__(self):
        self.timings = {}

    def measure(self, name):
        """装饰器：测量函数执行时间"""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start = time.time()
                result = func(*args, **kwargs)
                elapsed = (time.time() - start) * 1000

                if name not in self.timings:
                    self.timings[name] = []
                self.timings[name].append(elapsed)

                # 每10次输出一次平均值
                if len(self.timings[name]) % 10 == 0:
                    avg = sum(self.timings[name][-10:]) / 10
                    logger.info(f"[性能] {name}: {avg:.2f}ms (avg of last 10)")

                return result
            return wrapper
        return decorator

    def report(self):
        """输出性能报告"""
        logger.info("=== 性能分析报告 ===")
        for name, times in self.timings.items():
            if times:
                avg = sum(times) / len(times)
                max_time = max(times)
                logger.info(f"{name}: 平均 {avg:.2f}ms, 最大 {max_time:.2f}ms, 调用 {len(times)} 次")

profiler = PerformanceProfiler()

import queue

global Debug
Debug = False

global image_queue
image_queue = queue.Queue(maxsize=3)  # 从1增加到3

global result_queue
result_queue = queue.Queue(maxsize=3)  # 从1增加到3

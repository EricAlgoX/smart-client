import queue

global Debug
Debug = False

global image_queue 
image_queue = queue.Queue(maxsize=10)

global result_queue
result_queue = queue.Queue(maxsize=10)

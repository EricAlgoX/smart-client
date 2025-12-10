import queue

global Debug
Debug = False

global image_queue 
image_queue = queue.Queue(maxsize=1)

global result_queue
result_queue = queue.Queue(maxsize=1)

import os
import cv2
import time
import queue
import signal
import threading
import numpy as np
from flag import stop_event
from tabulate import tabulate
from flag import stop_event, exit_queue, signal_handler, ProcessingStatus
from inference import setup_inference, save_results_to_xml, preinfer, postinfer, draw_bboxes

def process_video_stream(args, mac_id, video_flv_url, cls_colors, status):
    while True and not stop_event.is_set():
        try:   
            session = setup_inference(args)
            cap = cv2.VideoCapture(video_flv_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  
            frame_count = 0
            missed_bicycle_count = 0 
            process_every_n_frames = 72

            while cap.isOpened():
                if stop_event.is_set():
                    print(f"Thread for {video_flv_url} is stopping...")
                    return
        
                ret, image = cap.read()
                if not ret:
                    break
                
                status.remove_failed(mac_id)
                status.add_processing(mac_id)
                
                if frame_count % process_every_n_frames == 0:
                    infer_input, ratio = preinfer(image, args)
                    postinfer_input = session.run(['output'], {'input': infer_input})
                    labels, scores, bboxes = postinfer(postinfer_input, ratio, args)

                    label_names = [args['class_names'][label] for label in labels]
                    if len(labels):
                        if ('bicycle' in label_names) or ('motorcycle' in label_names):
                            image_path = os.path.join('JPEGImages',  str(mac_id) + str(time.time()).replace('.', '')+'.jpg')
                            cv2.imwrite(image_path, image)

                            label_path = image_path.replace('JPEGImages', 'Annotations').replace('.jpg', '.xml')
                            save_results_to_xml(args, label_path, bboxes, labels, scores, image.shape)

                            draw_bboxes(image, bboxes, labels, scores, args['class_names'], cls_colors)
                            vi_image_path = image_path.replace('JPEGImages', 'Visualization')
                            cv2.imwrite(vi_image_path, image)

                            missed_bicycle_count = 0
                            process_every_n_frames = 12
                        else:
                            missed_bicycle_count += 1
                            
                            if missed_bicycle_count > 5: # 如果连续五次没有检测到 bicycle，则恢复为默认值 72
                                process_every_n_frames = 72

                frame_count = (frame_count + 1) % process_every_n_frames
            
            cap.release()
        except Exception as e:
            status.remove_processing(mac_id)
            status.add_failed(mac_id)
            print(f"Error processing {video_flv_url}: {e}")

if __name__ == '__main__':
    args = {'cuda': True,
            'onnx': 'elevator.onnx',
            'image_size': 512,
            'confidence': 0.6,
            'nms_thresh': 0.3,
            'class_names': ['person', 'bicycle', 'motorcycle'],

            'mac_id': [
                37021421581314000159,
                37021421581314000161,
                37021421581314000162,
                37021421581314000164,
                37021421581314000168,
                37021421581314000170,
                37021421581314000172,
                37021421581314000174,
                37021421581314000181,
                37021421581314000183,
                37021421581314000192,
                37021421581314000194,
                37021421581314000197,
                37021421581314000198,
                37021421581314000201,
                37021421581314000063,
                37021421581314000068,
                37021400001320070346,
                37021400001320070347,
                37021400001320070348,
                37021400001320070349,
                37021400001320070350,
                37021400001320070351,
                37021400001320070352,
                37021400001320070353,
                37021400001320070354,
                37021400001320070355,
                37021400001320070356,
                37021400001320070357,
                37021400001320070358,
                37021400001320070359,
                37021400001320070360,
                37021400001320070361,
                37021400001320070362,
                37021400001320070363,
                37021400001320070364,
                37021400001320070365,
                37021400001320070366,
                37021400001320070367,
                37021400001320070368,
                37021400001320070369,
                37021400001320070370,
                37021400001320070371,
                37021400001320070372,
                37021400001320070373
            ]
        }
    
    threads = []
    status = ProcessingStatus()
    signal.signal(signal.SIGINT, signal_handler)

    cls_colors = [tuple(np.random.randint(255, size=3).tolist()) for _ in range(len(args['class_names']))]
        
    for mac_id in args['mac_id']:
        status.add_failed(mac_id)
        url = "https://iot.beiangeovis.top:443/rtp/37021400002007615200_{}.live.flv".format(str(mac_id))
        thread = threading.Thread(target=process_video_stream, args=(args, mac_id, url, cls_colors, status))
        threads.append(thread)
        thread.start()

    while True:
        try:
            exit_queue.get(timeout=1)
            break
        except queue.Empty:
            data = []
            for mac_id in status.get_processing():
                data.append([mac_id, "Processing"])
            for mac_id in status.get_failed():
                data.append([mac_id, "Failed"])
            data = sorted(data)
            data.append(["Processing: ", len(status.get_processing())])

            formated_data = []
            for i in range(0, len(data), 3):
                row = data[i:i+3]
                formated_data.append(row)

            # 使用 tabulate 格式化输出
            # os.system('cls')
            print(tabulate(formated_data, 
                           headers=["mac_id                       Status", 
                                    "mac_id                       Status",
                                    "mac_id                       Status"
                                    ],
                           tablefmt="fancy_grid"),
                           end='\r')

    for thread in threads:
        thread.join()
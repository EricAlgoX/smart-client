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

def process_video_stream_image(args, mac_id, video_flv_url, cls_colors, status):
    os.makedirs('JPEGImages', exist_ok=True)
    os.makedirs('Annotations', exist_ok=True)
    os.makedirs('Visualization', exist_ok=True)
         
    while True and not stop_event.is_set():
        try:   
            session = setup_inference(args)
            cap = cv2.VideoCapture(video_flv_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            frame_count = 0
            missed_bicycle_count = 0 
            process_every_n_frames = 12

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
                    
                    if ('slagtruck' in label_names):
                        image_path = os.path.join('JPEGImages',  str(mac_id) + str(time.time()).replace('.', '')+'.jpg')
                        cv2.imwrite(image_path, image)

                        label_path = image_path.replace('JPEGImages', 'Annotations').replace('.jpg', '.xml')
                        save_results_to_xml(args, label_path, bboxes, labels, scores, image.shape)

                        draw_bboxes(image, bboxes, labels, scores, args['class_names'], cls_colors)
                        vi_image_path = image_path.replace('JPEGImages', 'Visualization')
                        cv2.imwrite(vi_image_path, image)

                        save_frames = True
                        missed_bicycle_count = 0
                        process_every_n_frames = 1
                    else:
                        missed_bicycle_count += 1
                        
                        if missed_bicycle_count > 5: # 如果连续五次没有检测到 bicycle，则恢复为默认值 12
                            save_frames = False
                            process_every_n_frames = 6

                frame_count = (frame_count + 1) % process_every_n_frames
            
            cap.release()
        except Exception as e:
            status.remove_processing(mac_id)
            status.add_failed(mac_id)
            print(f"Error processing {video_flv_url}: {e}")

def process_video_stream_video(args, mac_id, video_flv_url, cls_colors, status):
    os.makedirs('Video', exist_ok=True)
    
    try:
        session = setup_inference(args)
        cap = cv2.VideoCapture(video_flv_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        cnt = 0
        out = None
        video_count = 0  # 用于区分不同的视频文件
        save_frames = False

        while cap.isOpened():
            if stop_event.is_set():
                print(f"Thread for {video_flv_url} is stopping...")
                break

            ret, image = cap.read()
            if not ret:
                break

            status.remove_failed(mac_id)
            status.add_processing(mac_id)

            # 推理过程
            infer_input, ratio = preinfer(image, args)
            postinfer_input = session.run(['output'], {'input': infer_input})
            labels, scores, bboxes = postinfer(postinfer_input, ratio, args)

            if 'slagtruck' in [args['class_names'][label] for label in labels]:
                save_frames = True

            if save_frames:
                # 每获取到360帧就保存一次
                if cnt % 360 == 0:
                    if out:
                        out.release()  # 释放之前的视频文件
                        save_frames = False
                        
                    # 创建新的视频文件名
                    video_file_name = f'video/{str(mac_id)}_{video_count}.mp4'
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    out = cv2.VideoWriter(video_file_name, fourcc, fps, (width, height))

                    video_count += 1  # 增加视频文件计数

                # 绘制框并保存帧
                # draw_bboxes(image, bboxes, labels, scores, args['class_names'], cls_colors)
                out.write(image)
                cnt += 1

        # 最后释放资源
        if out:
            out.release()
        cap.release()

        print(f"Finished processing for {mac_id}, saved {video_count} videos.")

    except Exception as e:
        status.remove_processing(mac_id)
        status.add_failed(mac_id)
        print(f"Error processing {video_flv_url}: {e}")

if __name__ == '__main__':
    args = {'image': True, 'video': True,
            'cuda': True, 'onnx': 'slagtruck.onnx',
            'image_size': 640, 'confidence': 0.6, 'nms_thresh': 0.3,
            'class_names': ['slagtruck'],
            'mac_id': [ 37021401001310564916, 37021401001310385163]}
    
    threads = []
    status = ProcessingStatus()
    cls_colors = [(255, 255, 0)]
    signal.signal(signal.SIGINT, signal_handler)

    for mac_id in args['mac_id']:
        status.add_failed(mac_id)
        url = "https://iot.beiangeovis.top:443/rtp/37021400002000379004_{}.live.flv".format(str(mac_id))
        if args['image']:
            thread = threading.Thread(target=process_video_stream_image, args=(args, mac_id, url, cls_colors, status))
        
        if args['video']:
            thread = threading.Thread(target=process_video_stream_video, args=(args, mac_id, url, cls_colors, status))

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

            print(tabulate(formated_data, 
                           headers=["mac_id                       Status", 
                                    "mac_id                       Status",
                                    "mac_id                       Status"
                                    ],
                           tablefmt="fancy_grid"),
                           end='\r')

    for thread in threads:
        thread.join()
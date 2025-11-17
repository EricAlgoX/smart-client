import os
import cv2
import numpy as np
import onnxruntime
from xml.dom import minidom
import xml.etree.ElementTree as ET

def setup_inference(args):
    providers = [('CUDAExecutionProvider', {'device_id': 0})] if args['cuda'] else [('CPUExecutionProvider', {})]
    # print('Using CUDA' if args['cuda'] else 'Using CPU')

    return onnxruntime.InferenceSession(args['onnx'], providers=providers)

def preinfer(image, args):
    image_size = args['image_size']
    ratio = [image_size/image.shape[1], image_size/image.shape[0]]

    output = cv2.resize(image, (image_size, image_size))
    output = output.transpose([2, 0, 1]).astype(np.float32)
    output /= 255.
    output = np.expand_dims(output, 0)

    return output, ratio

def nms(bboxes, scores, nms_thresh):
    """"Pure Python NMS."""
    x1 = bboxes[:, 0]  #xmin
    y1 = bboxes[:, 1]  #ymin
    x2 = bboxes[:, 2]  #xmax
    y2 = bboxes[:, 3]  #ymax

    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(1e-10, xx2 - xx1)
        h = np.maximum(1e-10, yy2 - yy1)
        inter = w * h

        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-14)
        #reserve all the boundingbox whose ovr less than thresh
        inds = np.where(iou <= nms_thresh)[0]
        order = order[inds + 1]

    return keep

def postinfer(input, ratio, args):
    bboxes = input[0][:, :4]
    scores = input[0][:, 4:]

    labels = np.argmax(scores, axis=1)
    scores = scores[(np.arange(scores.shape[0]), labels)]
        
    keep = np.where(scores >= args['confidence'])
    bboxes = bboxes[keep]
    scores = scores[keep]
    labels = labels[keep]

    bboxes[..., [0, 2]] /= ratio[0]
    bboxes[..., [1, 3]] /= ratio[1]
    bboxes[..., [0, 2]] = np.clip(bboxes[..., [0, 2]], a_min=0., a_max=(args['image_size']/ratio[0]))
    bboxes[..., [1, 3]] = np.clip(bboxes[..., [1, 3]], a_min=0., a_max=(args['image_size']/ratio[1]))

    # NMS: Non-Maximum Suppression
    keep = np.zeros(len(bboxes), dtype=np.int32)
    for i in range(len(args['class_names'])):
        inds = np.where(labels == i)[0]
        if len(inds) == 0:
            continue
        c_bboxes = bboxes[inds]
        c_scores = scores[inds]
        c_keep = nms(c_bboxes, c_scores, args['nms_thresh'])
        keep[inds[c_keep]] = 1
    keep = np.where(keep > 0)
    scores = scores[keep]
    labels = labels[keep]
    bboxes = bboxes[keep]

    return labels, scores, bboxes

def save_results_to_xml(args, label_path, bboxes, labels, scores, shape):                       
    root = ET.Element("annotations")
    
    ET.SubElement(root, "folder").text = os.path.dirname(label_path)
    ET.SubElement(root, "filename").text = label_path.split('//')[-1].replace('.xml', '.jpg')
    
    size_elem = ET.SubElement(root, "size")
    ET.SubElement(size_elem, "width").text = str(shape[1])
    ET.SubElement(size_elem, "height").text = str(shape[0])
    ET.SubElement(size_elem, "depth").text = str(shape[2])

    for bbox, label, score in zip(bboxes, labels, scores):
        obj = ET.SubElement(root, "object")
        ET.SubElement(obj, "name").text = args['class_names'][label]
        ET.SubElement(obj, "score").text = str(score)

        bbox_elem = ET.SubElement(obj, "bndbox")
        ET.SubElement(bbox_elem, "xmin").text = str(int(bbox[0]))
        ET.SubElement(bbox_elem, "ymin").text = str(int(bbox[1]))
        ET.SubElement(bbox_elem, "xmax").text = str(int(bbox[2]))
        ET.SubElement(bbox_elem, "ymax").text = str(int(bbox[3]))

    xml_str = ET.tostring(root, encoding='utf-8')
    xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")

    with open(label_path, "w") as f:
        f.write(xml_str)

def display_fps(image, time):
    fps = f"fps:{round(1 / (time), 2)}"
    cv2.putText(image, fps, (0, 20), cv2.FONT_HERSHEY_COMPLEX, 1, (0, 0, 0), 1)

def draw_bboxes(image, bboxes, labels, scores, class_names, class_colors):
    for index, bbox in enumerate(bboxes):
        bbox = [int(point) for point in bbox]

        text = "%s:%s"%(class_names[labels[index]], str(round(float(scores[index]), 2)))
        (w, h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_COMPLEX, 1, 1)

        cv2.rectangle(image, (bbox[0], bbox[1]), (bbox[2], bbox[3]), class_colors[labels[index]], 2)
        cv2.rectangle(image, (bbox[0], bbox[1]), (bbox[0] + w, bbox[1] + h), class_colors[labels[index]], -1) 
        cv2.putText(image, text, (bbox[0], bbox[1]+h), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 255, 255), 1)
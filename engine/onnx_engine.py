"""ONNX Runtime 推理引擎"""

import cv2
import numpy as np
from typing import List, Dict
import onnxruntime as ort

from engine.base import BaseEngine
from utils.logger import logger


class OnnxEngine(BaseEngine):
    """基于 ONNX Runtime 的推理引擎，支持 YOLO 系列模型"""

    def __init__(self):
        self._session = None
        self._config = {}
        self._loaded = False
        self._input_name = None

    def load(self, config: dict) -> bool:
        """
        加载 ONNX 模型
        config 示例:
        {
            "model_path": "models/yolov8n.onnx",
            "class_names": ["person", "car"],
        }
        """
        model_path = config.get("model_path", "")
        if not model_path:
            logger.error("[OnnxEngine] 未指定 model_path")
            return False

        available = ort.get_available_providers()
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in available]
        
        self._config = config

        try:
            self._session = ort.InferenceSession(model_path, providers=providers or available)
            self._input_name = self._session.get_inputs()[0].name
            
            self._input_size = tuple(config.get("input_size", [640, 640]))
            self.input_height = self._input_size[0]
            self.input_width = self._input_size[1]
            
            self.confidence_thres = config.get("confidence", 0.3)
            self.iou_thres = config.get("nms_threholds", 0.5)
        
            self._loaded = True
            logger.info(f"[OnnxEngine] 已加载: {model_path} (provider={providers})")
            return True
        except Exception as e:
            logger.error(f"[OnnxEngine] 加载失败: {e}")
            return False

    def letterbox(self, img: np.ndarray, new_shape: tuple[int, int] = (640, 640)) -> tuple[np.ndarray, tuple[int, int]]:
        """Resize and reshape images while maintaining aspect ratio by adding padding.

        Args:
            img (np.ndarray): Input image to be resized.
            new_shape (tuple[int, int]): Target shape (height, width) for the image.

        Returns:
            img (np.ndarray): Resized and padded image.
            pad (tuple[int, int]): Padding values (top, left) applied to the image.
        """
        shape = img.shape[:2]  # current shape [height, width]
        # Scale ratio (new / old)
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])

        # Compute padding
        new_unpad = round(shape[1] * r), round(shape[0] * r)
        dw, dh = (new_shape[1] - new_unpad[0]) / 2, (new_shape[0] - new_unpad[1]) / 2  # wh padding

        if shape[::-1] != new_unpad:  # resize
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
        top, bottom = round(dh - 0.1), round(dh + 0.1)
        left, right = round(dw - 0.1), round(dw + 0.1)
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))

        return img, (top, left)
    
    def preprocess(self, image: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
        """Preprocess an input image before performing inference.

        Args:
            image (np.ndarray): BGR input image.

        Returns:
            image_data (np.ndarray): Preprocessed image data ready for inference with shape (1, 3, height, width).
            pad (tuple[int, int]): Padding values (top, left) applied during letterboxing.
        """
        # Convert the image color space from BGR to RGB
        img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        img, pad = self.letterbox(img, (self.input_width, self.input_height))

        # Normalize the image data by dividing it by 255.0
        image_data = np.array(img) / 255.0

        # Transpose the image to have the channel dimension as the first dimension
        image_data = np.transpose(image_data, (2, 0, 1))  # Channel first

        # Expand the dimensions of the image data to match the expected input shape
        image_data = image_data[None].astype(np.float32)

        return image_data, pad
    
    def postprocess(self, input_image: np.ndarray, output: list[np.ndarray], pad: tuple[int, int],
                    class_names, confidence: float, nms: float):
        """Perform post-processing on the model's output to extract detections.

        Args:
            input_image (np.ndarray): The original input image.
            output (list[np.ndarray]): The output arrays from the model.
            pad (tuple[int, int]): Padding values (top, left) used during letterboxing.
            class_names (list): Class name list.
            confidence (float): Confidence threshold for this call.
            nms (float): NMS threshold for this call.

        Returns:
            list[dict]: Detection results.
        """
        details = []

        # Transpose and squeeze the output to match the expected shape
        outputs = np.transpose(np.squeeze(output[0]))

        # Get the number of rows in the outputs array
        rows = outputs.shape[0]

        # Lists to store the bounding boxes, scores, and class IDs of the detections
        boxes = []
        scores = []
        class_ids = []

        # Use original image dims from the passed-in image (thread-safe — no self.img)
        img_height, img_width = input_image.shape[:2]

        # Calculate the scaling factors for the bounding box coordinates
        gain = min(self.input_height / img_height, self.input_width / img_width)
        outputs[:, 0] -= pad[1]
        outputs[:, 1] -= pad[0]

        # Iterate over each row in the outputs array
        for i in range(rows):
            # Extract the class scores from the current row
            classes_scores = outputs[i][4:]

            # Find the maximum score among the class scores
            max_score = np.amax(classes_scores)

            # If the maximum score is above the confidence threshold
            if max_score >= confidence:
                # Get the class ID with the highest score
                class_id = np.argmax(classes_scores)

                # Extract the bounding box coordinates from the current row
                x, y, w, h = outputs[i][0], outputs[i][1], outputs[i][2], outputs[i][3]

                # Calculate the scaled coordinates of the bounding box
                left = int((x - w / 2) / gain)
                top = int((y - h / 2) / gain)
                width = int(w / gain)
                height = int(h / gain)

                # Add the class ID, score, and box coordinates to the respective lists
                class_ids.append(class_id)
                scores.append(max_score)
                boxes.append([left, top, left+width, top+height])

        # Apply non-maximum suppression to filter out overlapping bounding boxes
        indices = cv2.dnn.NMSBoxes(boxes, scores, confidence, nms)
        if len(indices) > 0:
            for i in np.array(indices).flatten():
                cls_idx = class_ids[int(i)]
                cls_name = class_names[cls_idx] if cls_idx < len(class_names) else str(cls_idx)
                xmin, ymin, xmax, ymax = int(boxes[i][0]), int(boxes[i][1]), int(boxes[i][2]), int(boxes[i][3])
                details.append({
                    'class': cls_name,
                    'score': f"{scores[i]:.2f}",
                    'bbox': (xmin, ymin, xmax, ymax),
                    'coordinate': [[xmin, ymin], [xmax, ymax]],
                })

        return details
    
    def detect(self, image: np.ndarray, confidence: float = 0.3, nms: float = 0.5, **kwargs) -> List[Dict]:
        if not self._loaded or image is None:
            return []

        class_names = self._config.get("class_names", [])

        # Preprocess the image data (pass image explicitly — no instance state)
        img_data, pad = self.preprocess(image)

        # Run inference using the preprocessed image data
        outputs = self._session.run(None, {self._input_name: img_data})

        # Perform post-processing with explicit confidence/nms parameters
        logger.info(f"[OnnxEngine] 输入 {image.shape}, conf={confidence}, nms={nms}")
        return self.postprocess(image, outputs, pad, class_names, confidence, nms)

    def unload(self):
        self._session = None
        self._loaded = False
        self._input_name = None
        logger.info("[OnnxEngine] 已卸载")

    @property
    def name(self) -> str:
        return "ONNX"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

import requests
import cv2
import base64

class Inference:
    def __init__(self, api_url):
        self.api_url = api_url

    def run(self,
            frame,
            nms = 0.5,
            polygon = [],
            reset = False,
            timeout = None,
            confidence = 0.3,
            max_threshold = 100,
            ):
        """
        组装推理API参数，供APIClient调用
        :param confidence: 置信度
        :param max_det: 最大检测数
        :param polygon: 多边形围栏点集（原图像素坐标）
        :param timeout: 超时时间（秒）
        :return: dict
        """
        # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        _, buffer = cv2.imencode('.jpg', frame)

        data = {
            'image': base64.b64encode(buffer).decode('utf-8'),

            'nms': nms,
            'reset': reset,
            'track_id': None,
            'polygon': polygon,
            'timeout_mins': timeout,
            'confidence': confidence,
            'max_threshold': max_threshold
        }
        
        try:
            response = requests.post(self.api_url, json=data)
            
            # 检查HTTP状态码
            if response.status_code != 200:
                # 尝试获取详细的错误信息
                try:
                    error_detail = response.json()
                    if 'detail' in error_detail:
                        error_msg = f"HTTP {response.status_code}: {error_detail['detail']}"
                    else:
                        error_msg = f"HTTP {response.status_code}: {response.text}"
                except:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                
                # 抛出包含详细信息的异常
                raise Exception(error_msg)
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # 处理网络请求异常
            raise Exception(f"网络请求失败: {str(e)}")
        except Exception as e:
            # 重新抛出其他异常
            raise e
import requests
from fastapi.logger import logger


class RequestUtil:
    def __init__(self):
        self.session = requests.Session()

    # 第一是统一请求入口，封装get、post、put、delete等方法，所有请求都走这个工具类。
    def send_request(self, method, url, **kwargs):
        logger.info(f"请求: {method} {url}")
        response = self.session.request(method=method, url=url, **kwargs)
        logger.info(f"响应: {response.status_code}")
        return response

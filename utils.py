import time
import requests
import logging
from functools import wraps

# 配置日志（添加文件记录）
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fund_advisor.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def retry(retries=3, delay=2):
    """通用的重试装饰器，支持指数退避"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    wait_time = delay * (2 ** i)  # 指数退避
                    logger.warning(f"执行 {func.__name__} 失败 ({i+1}/{retries}): {e}，{wait_time}秒后重试...")
                    time.sleep(wait_time)
            logger.error(f"函数 {func.__name__} 最终执行失败: {last_exception}")
            raise last_exception
        return wrapper
    return decorator

def push_notification(title, content, token):
    """推送到 PushPlus（修复URL空格问题）"""
    if not token:
        logger.warning("未配置 PushPlus Token，跳过推送")
        return
    
    # 修复：移除 URL 末尾空格
    url = 'http://www.pushplus.plus/send'
    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown"
    }
    try:
        resp = requests.post(url, json=data, timeout=10)
        if resp.json().get("code") == 200:
            logger.info("推送通知成功")
        else:
            logger.error(f"推送失败: {resp.text}")
    except Exception as e:
        logger.error(f"推送请求异常: {e}")
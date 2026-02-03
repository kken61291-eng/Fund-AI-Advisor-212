import time
import logging
import functools
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout
from urllib3.exceptions import ProtocolError, RemoteDisconnected

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry(retries=3, backoff_factor=2):
    """
    增强版重试装饰器
    backoff_factor: 失败后等待时间的倍数 (2s, 4s, 8s...)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = 2 # 初始等待2秒
            
            for i in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except (RequestException, ConnectionError, Timeout, ProtocolError, RemoteDisconnected, Exception) as e:
                    last_exception = e
                    if i < retries:
                        sleep_time = delay * (backoff_factor ** i)
                        logger.warning(f"⚠️ 接口请求失败: {e}，{sleep_time}秒后重试 ({i+1}/{retries})...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"❌ 重试耗尽，最终失败: {e}")
            
            return None 
        return wrapper
    return decorator

def send_email(subject, content):
    """发送邮件功能 (保持不变)"""
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    import os

    sender = os.getenv('MAIL_USER')
    password = os.getenv('MAIL_PASS')
    
    if not sender or not password:
        logger.warning("未配置邮件账户，跳过发送")
        return

    receivers = [sender]

    try:
        message = MIMEText(content, 'html', 'utf-8')
        message['From'] = Header(f"AI Advisor <{sender}>", 'utf-8')
        message['To'] = Header("Commander", 'utf-8')
        message['Subject'] = Header(subject, 'utf-8')

        try:
            smtp_obj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        except:
            try:
                smtp_obj = smtplib.SMTP_SSL('smtp.163.com', 465)
            except:
                smtp_obj = smtplib.SMTP('smtp.gmail.com', 587)
                smtp_obj.starttls()

        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receivers, message.as_string())
        logger.info("邮件发送成功 📧")
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")

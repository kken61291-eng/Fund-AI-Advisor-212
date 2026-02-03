import time
import logging
import functools
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout
from http.client import RemoteDisconnected
# 引入 formataddr 用于规范邮件头
from email.utils import formataddr

try:
    from urllib3.exceptions import ProtocolError
except ImportError:
    class ProtocolError(Exception): pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def retry(retries=3, backoff_factor=2):
    """
    增强版重试装饰器
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = 2 
            for i in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except (RequestException, ConnectionError, Timeout, ProtocolError, RemoteDisconnected, Exception) as e:
                    last_exception = e
                    error_name = type(e).__name__
                    if i < retries:
                        sleep_time = delay * (backoff_factor ** i)
                        logger.warning(f"⚠️ {error_name}: 请求失败，{sleep_time}秒后重试 ({i+1}/{retries})...")
                        time.sleep(sleep_time)
                    else:
                        logger.error(f"❌ 重试耗尽，最终失败: {error_name} - {e}")
            return None 
        return wrapper
    return decorator

def send_email(subject, content):
    """
    发送邮件功能 (Header 格式修复版)
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    import os

    sender = os.getenv('MAIL_USER')
    password = os.getenv('MAIL_PASS')
    
    if not sender or not password:
        logger.warning("未配置邮件账户，跳过发送")
        return

    # 简单的收件人逻辑：发给自己
    receivers = [sender]

    try:
        message = MIMEText(content, 'html', 'utf-8')
        
        # [修复点] 使用 formataddr 构造标准的 From/To 头
        # 这样 QQ/腾讯企业邮箱就不会报 550 Invalid Header 了
        message['From'] = formataddr(("AI Advisor", sender))
        message['To'] = formataddr(("Commander", sender))
        
        message['Subject'] = Header(subject, 'utf-8')

        # 尝试连接常见邮箱端口
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

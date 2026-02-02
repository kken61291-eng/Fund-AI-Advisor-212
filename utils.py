import time
import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.utils import formataddr
from functools import wraps

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def retry(retries=3, delay=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"执行 {func.__name__} 失败 ({i+1}/{retries}): {e}")
                    time.sleep(delay)
            raise args[0] if args else Exception("Retry failed")
        return wrapper
    return decorator

def send_email(subject, content):
    """发送邮件通知 (QQ邮箱) - 支持 HTML"""
    mail_user = os.getenv("MAIL_USER")
    mail_pass = os.getenv("MAIL_PASS")
    
    if not mail_user or not mail_pass:
        logger.warning("未配置邮箱账号密码，跳过发送")
        return

    try:
        # 【关键修改】第二个参数改为 'html'，告诉邮箱渲染网页
        message = MIMEText(content, 'html', 'utf-8')
        
        message['From'] = formataddr(["AI基金投顾", mail_user])
        message['To'] = formataddr(["尊贵的投资者", mail_user])
        message['Subject'] = subject

        smtpObj = smtplib.SMTP_SSL('smtp.qq.com', 465)
        smtpObj.login(mail_user, mail_pass)
        smtpObj.sendmail(mail_user, [mail_user], message.as_string())
        smtpObj.quit()
        logger.info("邮件发送成功 📧")
    except Exception as e:
        logger.error(f"无法发送邮件: {e}")

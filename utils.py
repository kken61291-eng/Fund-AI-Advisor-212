import logging
import smtplib
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from functools import wraps
from datetime import datetime
import pytz

# --- 日志配置 ---
# 定义日志文件名
LOG_FILENAME = "latest_run.log"

def setup_logger():
    logger = logging.getLogger("FundAdvisor")
    logger.setLevel(logging.INFO)
    logger.handlers = []  # 清除旧的 handlers 防止重复打印

    # 格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # 1. 控制台输出 (Console Handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. 文件输出 (File Handler) - 每次运行覆盖模式 'w'
    file_handler = logging.FileHandler(LOG_FILENAME, mode='w', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

logger = setup_logger()

def get_beijing_time():
    utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)
    beijing_now = utc_now.astimezone(pytz.timezone('Asia/Shanghai'))
    return beijing_now

def retry(retries=3, delay=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == retries - 1:
                        logger.error(f"Function {func.__name__} failed after {retries} attempts: {e}")
                        raise e
                    logger.warning(f"Retrying {func.__name__} ({i+1}/{retries})... Error: {e}")
                    time.sleep(delay)
        return wrapper
    return decorator

def send_email(subject, html_content, attachment_path=None):
    """
    发送带附件的邮件
    """
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receiver = os.getenv("EMAIL_TO")
    
    if not sender or not password or not receiver:
        logger.warning("🚫 邮箱配置缺失，跳过发送。")
        return

    try:
        # 创建复合邮件对象
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = f"玄铁量化 <{sender}>"
        msg['To'] = receiver
        
        # 1. 添加 HTML 正文
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        
        # 2. 添加附件 (如果有)
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, "rb") as f:
                    # 读取日志文件
                    part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
                
                # 设置附件头信息
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                msg.attach(part)
                logger.info(f"📎 已添加附件: {attachment_path}")
            except Exception as e:
                logger.error(f"❌ 附件添加失败: {e}")

        # 发送
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        logger.info("📧 邮件(含附件)发送成功！")
        
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")

import logging
import time
import functools
import smtplib
import os
from email.mime.text import MIMEText
from email.header import Header

# 1. 配置全局日志格式 (详细模式)
# 格式包含: 时间 - 级别 - 文件名:行号 - 消息
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("FundAdvisor")

def retry(retries=3, delay=1):
    """
    一个支持重试次数(retries)和延迟时间(delay)的通用装饰器。
    支持指数退避策略 (Exponential Backoff)。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for i in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    # 如果不是最后一次尝试，则打印警告并等待
                    if i < retries:
                        wait_time = delay * (1 + i) # 线性递增等待，如 2s, 4s...
                        logger.warning(
                            f"⚠️ 函数 [{func.__name__}] 执行失败: {e} "
                            f"| 正在进行第 {i+1}/{retries} 次重试，等待 {wait_time}秒..."
                        )
                        time.sleep(wait_time)
                    else:
                        # 最后一次失败，打印错误日志 (但不抛出崩溃，除非逻辑需要)
                        logger.error(
                            f"❌ 函数 [{func.__name__}] 在 {retries} 次重试后彻底失败。 "
                            f"最终错误: {e}"
                        )
                        # 这里可以选择 raise 抛出异常让主程序捕获，
                        # 或者 return None 让流程继续。
                        # 为了防止线程崩溃，我们选择抛出异常，由上层 try-except 捕获
                        raise last_exception
            return None
        return wrapper
    return decorator

def send_email(subject, content):
    """
    发送邮件通知 (增强错误处理版)
    """
    sender = os.getenv("MAIL_USER")
    password = os.getenv("MAIL_PASS")
    
    if not sender or not password:
        logger.warning("未配置邮件账户 (MAIL_USER/MAIL_PASS)，跳过邮件发送。")
        return

    # 收件人默认发给自己
    receiver = sender
    
    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = f"Fund Advisor <{sender}>"
    message['To'] = receiver
    message['Subject'] = Header(subject, 'utf-8')

    try:
        # 尝试连接 SMTP 服务器 (支持主流邮箱)
        if "qq.com" in sender:
            smtp_server = "smtp.qq.com"
            smtp_port = 465
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        elif "163.com" in sender:
            smtp_server = "smtp.163.com"
            smtp_port = 465 # 或 25
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        elif "gmail.com" in sender:
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        else:
            # 默认尝试 163 配置
            smtp_server = "smtp.163.com"
            server = smtplib.SMTP_SSL(smtp_server, 465)

        server.login(sender, password)
        server.sendmail(sender, receiver, message.as_string())
        server.quit()
        logger.info("📧 邮件发送成功！")
        
    except smtplib.SMTPAuthenticationError:
        logger.error("邮件登录失败：用户名或授权码错误 (请检查 GitHub Secrets)")
    except Exception as e:
        logger.error(f"邮件发送未知错误: {e}")

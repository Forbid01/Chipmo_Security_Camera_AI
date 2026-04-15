import asyncio
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

# .env файл унших
load_dotenv()
logger = logging.getLogger(__name__)

def _send_email_sync(msg: MIMEMultipart):
    """
    SMTP холболтыг синхрон байдлаар гүйцэтгэх туслах функц.
    smtplib нь асинхрон биш тул thread-д ажиллуулах шаардлагатай.
    """
    mail_user = os.getenv("MAIL_USERNAME")
    mail_pass = os.getenv("MAIL_PASSWORD")

    if not mail_user or not mail_pass:
        raise ValueError("MAIL_USERNAME эсвэл MAIL_PASSWORD тохируулаагүй байна.")

    try:
        # Gmail-ийн стандарт SMTP порт 587
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()  # TLS нууцлал идэвхжүүлэх
            server.login(mail_user, mail_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"SMTP Error: {e}")
        raise e

async def send_otp_email(receiver_email: str, otp_code: str):
    """Нууц үг сэргээх OTP кодыг асинхрон байдлаар илгээнэ."""
    mail_from = os.getenv("MAIL_FROM", os.getenv("MAIL_USERNAME"))

    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background-color: #0f172a; color: #ffffff; text-align: center;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; padding: 30px; border-radius: 20px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
            <h2 style="color: #ef4444; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 20px;">
                Security.AI Authentication
            </h2>
            <p style="color: #94a3b8; font-size: 14px; margin-bottom: 30px;">
                Таны нууц үг сэргээх хүсэлт баталгаажлаа. Доорх кодыг ашиглан нэвтрэнэ үү.
            </p>
            <div style="background: #000000; padding: 20px; border-radius: 12px; border: 1px dashed #ef4444; margin-bottom: 30px;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 10px; color: #ffffff;">
                    {otp_code}
                </span>
            </div>
            <p style="color: #64748b; font-size: 11px; text-transform: uppercase;">
                Энэ код 15 минутын дараа хүчингүй болно.
            </p>
            <hr style="border: 0; border-top: 1px solid #334155; margin: 30px 0;">
            <footer style="font-size: 10px; color: #475569;">
                System Node: UB-SURV-V11 | Security.AI Automated Response
            </footer>
        </div>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = mail_from
    msg['To'] = receiver_email
    msg['Subject'] = "Security.AI: Password Recovery Code"
    msg.attach(MIMEText(html, 'html'))

    try:
        # FastAPI/Uvicorn-ийн event loop-ийг гацаахгүйн тулд thread-д ажиллуулна
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_email_sync, msg)
        logger.info(f"OTP sent successfully to {receiver_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP to {receiver_email}: {e}")
        return False

async def send_contact_email(name: str, email: str, subject: str, message: str):
    """Холбоо барих хүсэлтийг админ руу илгээнэ."""
    mail_from = os.getenv("MAIL_FROM", os.getenv("MAIL_USERNAME"))

    html = f"""
    <div style="font-family: sans-serif; padding: 20px; background-color: #f9f9f9; color: #333;">
        <h2 style="color: #ef4444; border-bottom: 2px solid #ef4444; padding-bottom: 10px;">
            Security.AI - Шинэ хүсэлт
        </h2>
        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
            <p><b>Илгээгч:</b> {name}</p>
            <p><b>Имэйл:</b> {email}</p>
            <p><b>Гарчиг:</b> {subject}</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p><b>Зурвас:</b></p>
            <p style="white-space: pre-wrap; line-height: 1.6;">{message}</p>
        </div>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = mail_from
    msg['To'] = mail_from  # Админ өөрөө хүлээж авна
    msg['Subject'] = f"Security.AI Contact: {subject}"
    msg.attach(MIMEText(html, 'html'))

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_email_sync, msg)
        logger.info(f"Contact email from {email} sent to admin.")
        return True
    except Exception as e:
        logger.error(f"Failed to send contact email: {e}")
        return False

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

async def send_otp_email(receiver_email: str, otp_code: str):
    """Нууц үг сэргээх 6 оронтой OTP кодыг хэрэглэгчийн имэйл рүү илгээнэ."""
    mail_user = os.getenv("MAIL_USERNAME")
    mail_pass = os.getenv("MAIL_PASSWORD")
    mail_from = os.getenv("MAIL_FROM")
    
    # OTP кодонд зориулсан "Cybersecurity" хэв маягтай HTML загвар
    html = f"""
    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background-color: #0f172a; color: #ffffff; text-align: center;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; padding: 30px; border-radius: 20px; border: 1px solid #334155; shadow: 0 10px 25px rgba(0,0,0,0.5);">
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
        # SMTP сервертэй холбогдох (Gmail)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(mail_user, mail_pass)
        server.send_message(msg)
        server.quit()
        logger.info(f"OTP sent successfully to {receiver_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        return False

async def send_contact_email(name: str, email: str, subject: str, message: str):
    # .env файлаас мэдээллээ авах
    mail_user = os.getenv("MAIL_USERNAME")
    mail_pass = os.getenv("MAIL_PASSWORD")
    mail_from = os.getenv("MAIL_FROM")
    
    # Имэйлийн агуулга бэлтгэх
    html = f"""
    <div style="font-family: sans-serif; padding: 20px; background-color: #f9f9f9;">
        <h2 style="color: #ef4444; border-bottom: 2px solid #ef4444; padding-bottom: 10px;">
            Security.AI - Шинэ холбоо барих хүсэлт
        </h2>
        <p><b>Илгээгчийн нэр:</b> {name}</p>
        <p><b>Имэйл хаяг:</b> {email}</p>
        <p><b>Гарчиг:</b> {subject}</p>
        <div style="background: white; padding: 15px; border-radius: 8px; margin-top: 10px;">
            <p><b>Зурвас:</b></p>
            <p style="white-space: pre-wrap;">{message}</p>
        </div>
        <footer style="margin-top: 20px; font-size: 12px; color: #888;">
            Энэхүү имэйл нь Security.AI системээс автоматаар илгээгдлээ.
        </footer>
    </div>
    """

    msg = MIMEMultipart()
    msg['From'] = mail_from
    msg['To'] = mail_from
    msg['Subject'] = f"Security.AI: {subject}"
    msg.attach(MIMEText(html, 'html'))

    try:
        # SMTP сервертэй холбогдох (Gmail)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # Нууцлал идэвхжүүлэх
        server.login(mail_user, mail_pass)
        server.send_message(msg)
        server.quit()
        logger.info("Email sent successfully via smtplib")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise e
import smtplib, ssl, email.utils, imaplib, email, uuid
from email.mime.text import MIMEText
from datetime import datetime, timezone
from app.core.config import get_settings
from app.core.logging import events

class EmailService:
    def __init__(self): self.s=get_settings()
    def send(self,to,subject,body):
        if self.s.TEST_MODE: events.event('OUTREACH_TEST',to=to,subject=subject); return 'TEST-'+uuid.uuid4().hex
        if not self.s.SMTP_HOST or not self.s.EMAIL_FROM: raise RuntimeError('SMTP is not configured')
        msg=MIMEText(body,'plain','utf-8'); msg['Subject']=subject; msg['From']=email.utils.formataddr((self.s.EMAIL_FROM_NAME,self.s.EMAIL_FROM)); msg['To']=to
        with smtplib.SMTP(self.s.SMTP_HOST,self.s.SMTP_PORT,timeout=20) as server:
            server.starttls(context=ssl.create_default_context())
            if self.s.SMTP_USERNAME: server.login(self.s.SMTP_USERNAME,self.s.SMTP_PASSWORD)
            server.send_message(msg)
        events.event('OUTREACH_SENT',email=to); return msg['Message-ID'] or uuid.uuid4().hex

    def fetch_replies(self):
        if not self.s.IMAP_HOST: return []
        results=[]
        with imaplib.IMAP4_SSL(self.s.IMAP_HOST,self.s.IMAP_PORT) as box:
            box.login(self.s.IMAP_USERNAME,self.s.IMAP_PASSWORD); box.select('INBOX')
            _,data=box.search(None,'UNSEEN')
            for num in data[0].split():
                _,msgdata=box.fetch(num,'(RFC822)'); msg=email.message_from_bytes(msgdata[0][1])
                body=''
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type()=='text/plain' and 'attachment' not in str(part.get('Content-Disposition')):
                            body=part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8','ignore'); break
                else: body=msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8','ignore')
                results.append({'from':email.utils.parseaddr(msg.get('From'))[1],'subject':msg.get('Subject',''),'body':body,'message_id':msg.get('Message-ID')})
        return results

"""
Vercel serverless function for the SMTP Test Tool -- plain Python format
(no Flask), so Vercel doesn't try to auto-detect a Flask app entrypoint.

Deployed at /api/send. A rewrite in vercel.json maps the front-end's
POST /send call to this function.
"""

import json
import re
import smtplib
import socket
from http.server import BaseHTTPRequestHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def send_test_email(data):
    """Validate input and send one email. Returns (payload_dict, status_code)."""
    smtp_host = (data.get("smtp_host") or "").strip()
    smtp_port_raw = data.get("smtp_port")
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    sender_name = (data.get("sender_name") or "").strip()
    sender_email = (data.get("sender_email") or "").strip() or username
    recipient = (data.get("recipient") or "").strip()
    subject = (data.get("subject") or "SMTP Test").strip()
    html_body = data.get("html") or "<p>This is a test email.</p>"

    errors = {}
    if not smtp_host:
        errors["smtp_host"] = "Host is required"
    try:
        smtp_port = int(smtp_port_raw)
        if not (1 <= smtp_port <= 65535):
            raise ValueError()
    except (TypeError, ValueError):
        errors["smtp_port"] = "Port must be a number between 1 and 65535"
        smtp_port = None
    if not EMAIL_RE.match(username):
        errors["username"] = "Enter a valid username email"
    if not password:
        errors["password"] = "Password is required"
    if not EMAIL_RE.match(recipient):
        errors["recipient"] = "Enter a valid recipient email"
    if sender_email and not EMAIL_RE.match(sender_email):
        errors["sender_email"] = "Enter a valid sender email"

    if errors:
        return {"error": "Validation failed", "fields": errors}, 400

    msg = MIMEMultipart()
    msg["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    server = None
    try:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=9)
        server.ehlo()
        if server.has_extn("STARTTLS"):
            server.starttls()
            server.ehlo()
        server.login(username, password)
        server.sendmail(sender_email, [recipient], msg.as_string())
        return {"message": f"Email sent to {recipient}."}, 200

    except smtplib.SMTPAuthenticationError:
        return {"error": "Authentication failed. Check username/password."}, 401
    except smtplib.SMTPConnectError:
        return {"error": f"Could not connect to {smtp_host}:{smtp_port}."}, 502
    except (socket.timeout, TimeoutError):
        return {"error": "Connection timed out."}, 504
    except smtplib.SMTPException as e:
        return {"error": f"SMTP error: {e}"}, 502
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}, 500
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            data = {}

        payload, status = send_test_email(data)

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.end_headers()

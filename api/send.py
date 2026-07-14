"""
Vercel serverless function for the SMTP Test Tool.

Deployed at /api/send. A rewrite in vercel.json maps the front-end's
POST /send call to this function, so the HTML doesn't need to change.
"""

import re
import smtplib
import socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from flask import Flask, request, jsonify

app = Flask(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/send", methods=["POST"])
@app.route("/api/send", methods=["POST"])
def send_email():
    data = request.get_json(silent=True) or {}

    # ---- Extract + validate fields (mirrors the front-end validation) ----
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
        return jsonify(error="Validation failed", fields=errors), 400

    # ---- Build the message ----
    msg = MIMEMultipart()
    msg["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    # ---- Connect and send ----
    server = None
    try:
        # Serverless functions have a hard execution time limit, so keep
        # the socket timeout well under it.
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=9)
        server.ehlo()
        if server.has_extn("STARTTLS"):
            server.starttls()
            server.ehlo()
        server.login(username, password)
        server.sendmail(sender_email, [recipient], msg.as_string())
        return jsonify(message=f"Email sent to {recipient}."), 200

    except smtplib.SMTPAuthenticationError:
        return jsonify(error="Authentication failed. Check username/password."), 401
    except smtplib.SMTPConnectError:
        return jsonify(error=f"Could not connect to {smtp_host}:{smtp_port}."), 502
    except (socket.timeout, TimeoutError):
        return jsonify(error="Connection timed out."), 504
    except smtplib.SMTPException as e:
        return jsonify(error=f"SMTP error: {e}"), 502
    except Exception as e:
        return jsonify(error=f"Unexpected error: {e}"), 500
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass

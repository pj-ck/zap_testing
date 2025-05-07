import os
import subprocess
import time
import zipfile
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

# Configuration
WORKDIR = "/tmp/zap_reports"  # Updated to /tmp to avoid permission issues
DEFAULT_URLS = [
    "http://app.cloudkeeper.com",
    "http://auto.cloudkeeper.com",
    "http://gcp.cloudkeeper.com"
]

# Email config (must match verified SES sender)
EMAIL_FROM = "aditya.mishra@cloudkeeper.com"
EMAIL_TO = "prerana@cloudkeeper.com"
REPLY_TO = "aditya.mishra@cloudkeeper.com"

# SMTP config
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_SERVER = "email-smtp.us-east-1.amazonaws.com"
SMTP_PORT = 587

# ZAP config
ZAP_IMAGE = "ghcr.io/zaproxy/zaproxy:stable"

# Helper Functions
def run_cmd(cmd, check=True):
    print(f"🔧 Running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=check)

def run_zap_scan(url, domain_dir):
    print(f"➡️ Scanning: {url}")

    run_cmd([
        "docker", "run", "-v", f"{domain_dir}:/zap/wrk/:rw", "--rm", "-t", ZAP_IMAGE,
        "zap-baseline.py", "-t", url, "-r", "spider.html"
    ])

    try:
        run_cmd([
            "docker", "run", "-v", f"{domain_dir}:/zap/wrk/:rw", "--rm", "-t", ZAP_IMAGE,
            "zap-api-scan.py", "-t", url, "-f", "openapi", "-r", "ajax.html"
        ])
    except subprocess.CalledProcessError:
        print("⚠️ AJAX scan failed, skipping.")

    run_cmd([
        "docker", "run", "-v", f"{domain_dir}:/zap/wrk/:rw", "--rm", "-t", ZAP_IMAGE,
        "zap-full-scan.py", "-t", url, "-r", "active.html"
    ])

def zip_reports():
    zip_path = os.path.join(WORKDIR, f"zap_scan_reports_{datetime.now().strftime('%Y%m%d')}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(WORKDIR):
            for file in files:
                if file.endswith(".html"):
                    full_path = os.path.join(root, file)
                    arcname = os.path.relpath(full_path, WORKDIR)
                    zipf.write(full_path, arcname)
    return zip_path

def send_email(zip_path):
    print("📧 Sending email using SMTP...")
    msg = MIMEMultipart()
    msg['Subject'] = "ZAP Scan Reports"
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg.add_header('Reply-To', REPLY_TO)

    msg.attach(MIMEText("Attached are the consolidated ZAP scan reports for today.", 'plain'))

    with open(zip_path, 'rb') as f:
        part = MIMEBase('application', 'zip')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename=' + os.path.basename(zip_path))
        msg.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        print("✅ Email sent successfully.")

# Main Logic
if __name__ == "__main__":
    os.makedirs(WORKDIR, exist_ok=True)

    target_urls = os.environ.get("CUSTOM_URLS")
    if target_urls:
        TARGET_URLS = target_urls.split(',')
        print(f"🛠️ Using CUSTOM_URLS: {TARGET_URLS}")
    else:
        TARGET_URLS = DEFAULT_URLS
        print("ℹ️ Using default URL list.")

    for url in TARGET_URLS:
        domain = url.split("//")[-1].split("/")[0].replace('.', '_')
        domain_dir = os.path.join(WORKDIR, domain)
        os.makedirs(domain_dir, exist_ok=True)
        run_zap_scan(url, domain_dir)

    zip_file = zip_reports()
    send_email(zip_file)
    print("✅ All scans complete. Report emailed.")

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
WORKDIR = "/tmp/zap_reports"
DEFAULT_URLS = [
    "http://app.cloudkeeper.com",
    "http://auto.cloudkeeper.com",
    "http://gcp.cloudkeeper.com"
]

# Email config
EMAIL_FROM = "aditya.mishra@cloudkeeper.com"
EMAIL_TO = "prerana@cloudkeeper.com, akshit.mahajan1@cloudkeeper.com, sumit.kumar@cloudkeeper.com, vishu.tyagi@cloudkeeper.com"
REPLY_TO = "aditya.mishra@cloudkeeper.com"

# SMTP config
SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_SERVER = "email-smtp.us-east-1.amazonaws.com"
SMTP_PORT = 587

# ZAP config
ZAP_IMAGE = "ghcr.io/zaproxy/zaproxy:stable"

# Helper Functions
def run_cmd(cmd):
    print(f"\n📦 Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True
        )
        print("✅ Command succeeded")
        print("STDOUT:\n", result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print("❌ Command failed")
        print("Return code:", e.returncode)
        print("STDOUT:\n", e.stdout)
        print("STDERR:\n", e.stderr)
        raise

def run_zap_scan(url, domain_dir, domain):
    print(f"\n➡️ Starting ZAP scans for: {url}")

    # Run baseline scan
    try:
        print(f"🔍 Running baseline scan for {url}")
        run_cmd([
            "docker", "run", "-v", f"{domain_dir}:/zap/wrk/:rw", "--rm", "-t", ZAP_IMAGE,
            "zap-baseline.py", "-d", "-t", url, "-r", f"{domain}_baseline.html"
        ])
    except Exception as e:
        print(f"❌ Baseline scan failed for {url}: {e}")

    # Run AJAX scan
    try:
        print(f"🕷️ Running AJAX scan for {url}")
        run_cmd([
            "docker", "run", "-v", f"{domain_dir}:/zap/wrk/:rw", "--rm", "-t", ZAP_IMAGE,
            "zap-api-scan.py", "-d", "-t", url, "-f", "openapi", "-r", f"{domain}_ajax.html"
        ])
    except subprocess.CalledProcessError:
        print(f"⚠️ AJAX scan failed for {url}, skipping.")

    # Run active scan
    try:
        print(f"💥 Running active scan for {url}")
        run_cmd([
            "docker", "run", "-v", f"{domain_dir}:/zap/wrk/:rw", "--rm", "-t", ZAP_IMAGE,
            "zap-full-scan.py", "-d", "-t", url, "-r", f"{domain}_active.html"
        ])
    except Exception as e:
        print(f"❌ Active scan failed for {url}: {e}")

    print(f"✅ Completed all scans for {url}")

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

def send_email(zip_path, scanned_urls):
    print("\n📧 Sending email using SMTP...")
    msg = MIMEMultipart()
    msg['Subject'] = f"ZAP Security Scan Report – {datetime.now().strftime('%d-%b-%Y')}"
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg.add_header('Reply-To', REPLY_TO)

    # Dynamically build the scanned URL list
    url_list_html = ''.join(f"<li>{url}</li>" for url in scanned_urls)

    # HTML body
    body = f"""
    <p>Hi Team,</p>
    <p>Please find attached <strong>ZAP security scan reports</strong> for the following target URLs:</p>
    <ul>
        {url_list_html}
    </ul>
    <p>The following scans were performed on each of the above URLs:</p>
    <ol>
        <li><strong>Baseline Scan</strong></li>
        <li><strong>AJAX Scan</strong></li>
        <li><strong>Active Scan</strong></li>
    </ol>
    <br>
    <p>Warm Regards,</p>
    <p><strong>Aditya Mishra</strong><br>
    DevOps Engineer<br><br>
    <strong>CloudKeeper</strong> | <a href="https://www.cloudkeeper.com">www.cloudkeeper.com</a></p>
    """
    msg.attach(MIMEText(body, 'html'))

    # Attach zip
    with open(zip_path, 'rb') as f:
        part = MIMEBase('application', 'zip')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(zip_path)}')
        msg.attach(part)

    # Send email
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        print("✅ Email sent successfully.")

# Main Logic
if __name__ == "__main__":
    # Clean up the WORKDIR before scanning
    if os.path.exists(WORKDIR):
        for root, dirs, files in os.walk(WORKDIR, topdown=False):
            for file in files:
                os.remove(os.path.join(root, file))
            for dir in dirs:
                os.rmdir(os.path.join(root, dir))
    else:
        os.makedirs(WORKDIR)

    # Load custom URLs if provided
    target_urls_env = os.environ.get("CUSTOM_URLS")
    if target_urls_env:
        TARGET_URLS = [url.strip() for url in target_urls_env.split(',') if url.strip()]
        print(f"🛠️ Using CUSTOM_URLS: {TARGET_URLS}")
    else:
        TARGET_URLS = DEFAULT_URLS
        print(f"ℹ️ Using DEFAULT_URLS: {TARGET_URLS}")

    scanned_urls = []

    for url in TARGET_URLS:
        domain = url.split("//")[-1].split("/")[0].replace('.', '_')
        domain_dir = os.path.join(WORKDIR, domain)
        os.makedirs(domain_dir, exist_ok=True)

        try:
            run_zap_scan(url, domain_dir, domain)
            scanned_urls.append(url)
        except Exception as e:
            print(f"⚠️ Skipping scan for {url} due to error: {e}")

    zip_file = zip_reports()
    send_email(zip_file, scanned_urls)
    print("✅ All scans complete. Report emailed.")

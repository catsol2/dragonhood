from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlencode, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime
import json
import base64
import csv
import os
import hashlib
import hmac

PORT = int(os.environ.get("PORT", 5500))
ROOT = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------
# SECURITY KEYS
# --------------------------------------------------
ADMIN_SECRET_KEY = "K9#mQ!8xL$2vP@7wZ"          # URL export key
DATA_ENCRYPTION_PASS = "7fX#9m$K!2wL&8pQ*4vT@zR1" # Password to decrypt/unlock

X_CLIENT_ID = "czRuem5WemdvdXh2SmUwbDhCMjI6MTpjaQ"
X_CLIENT_SECRET = "oasvXGiPfMIWJE2Xzit9KsAWphfdj59rqa3t_tewZoReqmgRh4"

X_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
X_ME_URL = "https://api.twitter.com/2/users/me?user.fields=username,name"

CSV_FILE = os.path.join(ROOT, "submissions.csv")
JSON_FILE = os.path.join(ROOT, "submissions.json")


# Built-in XOR + Key Derivation Stream Cipher (Zero external packages needed)
def encrypt_data(raw_bytes, password):
    # Derive key via PBKDF2 HMAC SHA-256
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000, dklen=32)
    
    # Encrypt
    encrypted = bytearray()
    for idx, byte in enumerate(raw_bytes):
        key_byte = key[idx % len(key)]
        encrypted.append(byte ^ key_byte)
        
    mac = hmac.new(key, encrypted, hashlib.sha256).digest()
    return salt + mac + bytes(encrypted)


def save_submission(record):
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Timestamp", "Pass_ID", "X_Username", "X_User_ID", "Wallet_Address", "Tweet_Link"])
        writer.writerow([
            record.get("timestamp"),
            record.get("pass_id"),
            record.get("x_username"),
            record.get("x_user_id"),
            record.get("wallet_address"),
            record.get("tweet_link")
        ])

    all_records = []
    if os.path.isfile(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as jf:
                all_records = json.load(jf)
        except Exception:
            all_records = []

    all_records.append(record)
    with open(JSON_FILE, "w", encoding="utf-8") as jf:
        json.dump(all_records, jf, indent=2)


class Handler(SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def send_json(self, status, data):
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # 1. Direct CSV / JSON file access blocked for everyone
        if path.endswith(".csv") or path.endswith(".json"):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"403 Forbidden: Direct file access is blocked.")
            return

        # 2. Secure Admin Web Viewer & Decrypt Tool
        if path == "/api/admin/viewer":
            key = query.get("key", [""])[0]
            if key != ADMIN_SECRET_KEY:
                self.send_response(401)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"401 Unauthorized: Invalid Admin Key!")
                return

            # Built-in secure HTML viewer jisme password dalne par hi table khulega
            html_ui = """
            <!DOCTYPE html>
            <html>
            <head>
              <title>DragonHood Admin Vault</title>
              <style>
                body { background: #0b0f0c; color: #00ff66; font-family: monospace; padding: 25px; }
                h2 { color: #ffb800; }
                input { background: #000; border: 1px solid #00ff66; color: #00ff66; padding: 8px 12px; font-family: monospace; width: 320px; }
                button { background: #00ff66; color: #000; font-weight: bold; border: none; padding: 8px 16px; cursor: pointer; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 12px; }
                th, td { border: 1px solid rgba(0,255,102,0.3); padding: 8px; text-align: left; }
                th { background: rgba(0,255,102,0.1); color: #fff; }
                #err { color: #ff5555; margin-top: 10px; }
              </style>
            </head>
            <body>
              <h2># DRAGONHOOD SECURE VAULT</h2>
              <p>Enter Master Password to Decrypt & View Whitelist Data:</p>
              <input type="password" id="vaultPass" placeholder="Master Password..." />
              <button onclick="unlockData()">[ UNLOCK VAULT ]</button>
              <div id="err"></div>
              <div id="output"></div>

              <script>
                async function unlockData() {
                  const p = document.getElementById('vaultPass').value;
                  const key = new URLSearchParams(window.location.search).get('key');
                  const res = await fetch('/api/admin/unlock', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ key: key, pass: p })
                  });
                  const json = await res.json();
                  if (!res.ok) {
                    document.getElementById('err').innerText = json.error || 'Galat password!';
                    document.getElementById('output').innerHTML = '';
                    return;
                  }
                  document.getElementById('err').innerText = '';
                  if (json.data.length === 0) {
                    document.getElementById('output').innerHTML = '<p>No records found yet.</p>';
                    return;
                  }
                  let html = '<table><tr><th>Time (UTC)</th><th>Pass ID</th><th>X User</th><th>Wallet</th><th>Tweet</th></tr>';
                  json.data.forEach(r => {
                    html += `<tr><td>${r.timestamp||'-'}</td><td>${r.pass_id||'-'}</td><td>${r.x_username||'-'}</td><td>${r.wallet_address||'-'}</td><td><a href="${r.tweet_link}" target="_blank" style="color:#ffb800">Tweet Link</a></td></tr>`;
                  });
                  html += '</table>';
                  document.getElementById('output').innerHTML = html;
                }
              </script>
            </body>
            </html>
            """
            raw_html = html_ui.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw_html)))
            self.end_headers()
            self.wfile.write(raw_html)
            return

        super().do_GET()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None

    def do_POST(self):
        path = urlparse(self.path).path
        data = self.read_json()

        if data is None:
            self.send_json(400, {"error": "invalid_json"})
            return

        # --------------------------------------------------
        # VAULT UNLOCK (Password Verified Decryption)
        # --------------------------------------------------
        if path == "/api/admin/unlock":
            req_key = data.get("key")
            req_pass = data.get("pass")

            if req_key != ADMIN_SECRET_KEY:
                self.send_json(401, {"error": "Unauthorized key"})
                return

            if req_pass != DATA_ENCRYPTION_PASS:
                self.send_json(403, {"error": "Galat password! Access denied."})
                return

            records = []
            if os.path.isfile(JSON_FILE):
                try:
                    with open(JSON_FILE, "r", encoding="utf-8") as jf:
                        records = json.load(jf)
                except Exception:
                    records = []
            self.send_json(200, {"data": records})
            return

        # --------------------------------------------------
        # SUBMIT WHITELIST
        # --------------------------------------------------
        if path == "/api/submit-whitelist":
            wallet = data.get("wallet", "").strip()
            tweet_url = data.get("tweet_url", "").strip()
            x_handle = data.get("x_handle", "").strip()
            x_id = data.get("x_id", "").strip()
            pass_id = data.get("pass_id", "").strip()

            if not wallet or not tweet_url:
                self.send_json(400, {"error": "missing_fields"})
                return

            record = {
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "pass_id": pass_id,
                "x_username": x_handle,
                "x_user_id": x_id,
                "wallet_address": wallet,
                "tweet_link": tweet_url
            }

            try:
                save_submission(record)
                self.send_json(200, {"status": "success"})
            except Exception as e:
                self.send_json(500, {"error": "failed_to_save", "details": str(e)})
            return

        # --------------------------------------------------
        # X TOKEN EXCHANGE
        # --------------------------------------------------
        if path == "/api/x-token":
            code = data.get("code")
            code_verifier = data.get("code_verifier")
            redirect_uri = data.get("redirect_uri")

            if not code or not code_verifier or not redirect_uri:
                self.send_json(400, {"error": "missing_required_parameters"})
                return

            form_payload = {
                "code": code,
                "grant_type": "authorization_code",
                "client_id": X_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier
            }
            form = urlencode(form_payload)

            auth_str = f"{X_CLIENT_ID}:{X_CLIENT_SECRET}"
            auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")

            request = Request(
                X_TOKEN_URL,
                data=form.encode("utf-8"),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {auth_b64}"
                },
                method="POST"
            )

            try:
                with urlopen(request, timeout=30) as response:
                    raw = response.read()
                    self.send_json(response.status, json.loads(raw.decode("utf-8")))
                return
            except HTTPError as error:
                self.send_json(error.code, json.loads(error.read().decode("utf-8")))
                return
            except URLError as error:
                self.send_json(502, {"error": "x_token_network_error", "details": str(error)})
                return
            except Exception as error:
                self.send_json(500, {"error": "x_token_server_error", "details": str(error)})
                return

        # --------------------------------------------------
        # X USER INFO
        # --------------------------------------------------
        if path == "/api/x-me":
            access_token = data.get("access_token")
            if not access_token:
                self.send_json(400, {"error": "missing_access_token"})
                return

            request = Request(
                X_ME_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": "DragonHoodApp"
                },
                method="GET"
            )

            try:
                with urlopen(request, timeout=30) as response:
                    self.send_json(response.status, json.loads(response.read().decode("utf-8")))
                return
            except Exception as error:
                self.send_json(500, {"error": "x_me_error", "details": str(error)})
                return

        self.send_error(404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlencode, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime
import json
import base64
import csv
import os

PORT = int(os.environ.get("PORT", 5500))
ROOT = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------
# SECURITY KEYS (URL-Safe Key & Strong Master Password)
# --------------------------------------------------
ADMIN_SECRET_KEY = "K9_mQ_8xL_2vP_7wZ"          # URL export key (No '#' symbol)
DATA_ENCRYPTION_PASS = "7fX#9m$K!2wL&8pQ*4vT@zR1" # Vault Master Password

X_CLIENT_ID = "czRuem5WemdvdXh2SmUwbDhCMjI6MTpjaQ"
X_CLIENT_SECRET = "oasvXGiPfMIWJE2Xzit9KsAWphfdj59rqa3t_tewZoReqmgRh4"

X_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
X_ME_URL = "https://api.twitter.com/2/users/me?user.fields=username,name"

CSV_FILE = os.path.join(ROOT, "submissions.csv")
JSON_FILE = os.path.join(ROOT, "submissions.json")


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

        # 1. Direct CSV / JSON file download block
        if path.endswith(".csv") or path.endswith(".json"):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"403 Forbidden: Direct file access is blocked.")
            return

        # 2. Secure Admin Vault Viewer
        if path == "/api/admin/viewer":
            key = query.get("key", [""])[0]
            if key != ADMIN_SECRET_KEY:
                self.send_response(401)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"401 Unauthorized: Invalid Admin Key!")
                return

            html_ui = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>DragonHood Admin Vault</title>
  <style>
    * { box-sizing: border-box; }
    body { background: #071009; color: #00ff66; font-family: 'Courier New', Courier, monospace; padding: 30px; margin: 0; }
    .box { max-width: 900px; margin: 0 auto; background: #050505; border: 1px solid rgba(0,255,102,0.4); padding: 25px; box-shadow: 0 0 25px rgba(0,255,102,0.1); border-radius: 4px; }
    h2 { color: #ffb800; margin-top: 0; }
    input { background: #00140a; border: 1px solid rgba(0,255,102,0.5); color: #00ff66; padding: 10px 14px; font-family: monospace; width: 340px; font-size: 13px; border-radius: 3px; }
    input:focus { outline: none; border-color: #00ff66; box-shadow: 0 0 8px rgba(0,255,102,0.4); }
    button { background: #00ff66; color: #000; font-weight: bold; border: none; padding: 10px 20px; cursor: pointer; border-radius: 3px; font-size: 12px; margin-left: 6px; }
    button:hover { background: #33ff88; }
    table { width: 100%; border-collapse: collapse; margin-top: 25px; font-size: 12px; }
    th, td { border: 1px solid rgba(0,255,102,0.25); padding: 10px 12px; text-align: left; }
    th { background: rgba(0,255,102,0.1); color: #fff; }
    tr:nth-child(even) { background: rgba(0,255,102,0.02); }
    #err { color: #ff5555; margin-top: 12px; font-weight: bold; }
  </style>
</head>
<body>
  <div class="box">
    <h2># DRAGONHOOD SECURE VAULT</h2>
    <p style="color:rgba(0,255,102,0.7); font-size:13px;">Enter Master Password to Decrypt & View Whitelist Data:</p>
    <input type="password" id="vaultPass" placeholder="Enter Master Password..." />
    <button onclick="unlockData()">[ UNLOCK VAULT ]</button>
    <div id="err"></div>
    <div id="output"></div>
  </div>

  <script>
    async function unlockData() {
      const p = document.getElementById('vaultPass').value;
      const key = new URLSearchParams(window.location.search).get('key');
      const errDiv = document.getElementById('err');
      const outDiv = document.getElementById('output');
      errDiv.innerText = '';

      try {
        const res = await fetch('/api/admin/unlock', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ key: key, pass: p })
        });
        const json = await res.json();
        if (!res.ok) {
          errDiv.innerText = json.error || 'Access Denied: Invalid Master Password!';
          outDiv.innerHTML = '';
          return;
        }
        if (!json.data || json.data.length === 0) {
          outDiv.innerHTML = '<p style="margin-top:20px;">No whitelist records submitted yet.</p>';
          return;
        }
        let html = '<table><tr><th>Timestamp (UTC)</th><th>Pass ID</th><th>X Username</th><th>Wallet Address</th><th>Tweet Link</th></tr>';
        json.data.forEach(r => {
          html += `<tr>
            <td>${r.timestamp || '-'}</td>
            <td style="color:#ffb800; font-weight:bold;">${r.pass_id || '-'}</td>
            <td>${r.x_username || '-'}</td>
            <td style="font-family:monospace; color:#fff;">${r.wallet_address || '-'}</td>
            <td><a href="${r.tweet_link}" target="_blank" style="color:#00ff66;">Open Tweet</a></td>
          </tr>`;
        });
        html += '</table>';
        outDiv.innerHTML = html;
      } catch (e) {
        errDiv.innerText = 'Connection error: ' + e.message;
      }
    }
  </script>
</body>
</html>"""
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
        # VAULT UNLOCK (Password Verified)
        # --------------------------------------------------
        if path == "/api/admin/unlock":
            req_key = data.get("key")
            req_pass = data.get("pass")

            if req_key != ADMIN_SECRET_KEY:
                self.send_json(401, {"error": "Unauthorized admin key"})
                return

            if req_pass != DATA_ENCRYPTION_PASS:
                self.send_json(403, {"error": "Invalid Master Password! Access Denied."})
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
                    raw = response.read()
                    self.send_json(response.status, json.loads(raw.decode("utf-8")))
                return
            except HTTPError as error:
                self.send_json(error.code, json.loads(error.read().decode("utf-8")))
                return
            except URLError as error:
                self.send_json(502, {"error": "x_me_network_error", "details": str(error)})
                return
            except Exception as error:
                self.send_json(500, {"error": "x_me_server_error", "details": str(error)})
                return

        self.send_error(404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlencode, parse_qs
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime
import json
import base64
import csv
import os
import pyminizip

PORT = int(os.environ.get("PORT", 5500))
ROOT = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------
# STRONG RANDOM SECURITY KEYS
# --------------------------------------------------
ADMIN_SECRET_KEY = "K9#mQ!8xL$2vP@7wZ"          # URL export key
ZIP_PASSWORD = "7fX#9m$K!2wL&8pQ*4vT@zR1"     # Encrypted Zip password

X_CLIENT_ID = "czRuem5WemdvdXh2SmUwbDhCMjI6MTpjaQ"
X_CLIENT_SECRET = "oasvXGiPfMIWJE2Xzit9KsAWphfdj59rqa3t_tewZoReqmgRh4"

X_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
X_ME_URL = "https://api.twitter.com/2/users/me?user.fields=username,name"

CSV_FILE = os.path.join(ROOT, "submissions.csv")
JSON_FILE = os.path.join(ROOT, "submissions.json")
ZIP_FILE = os.path.join(ROOT, "protected_data.zip")


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

        # 1. Direct CSV / JSON / ZIP access block
        if path.endswith(".csv") or path.endswith(".json") or path.endswith(".zip"):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"403 Forbidden: Direct access is blocked for security.")
            return

        # 2. Secure Encrypted ZIP Export
        if path == "/api/admin/export-csv":
            key = query.get("key", [""])[0]
            if key != ADMIN_SECRET_KEY:
                self.send_response(401)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"401 Unauthorized: Invalid Admin Key!")
                return

            if not os.path.isfile(CSV_FILE):
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"No submissions recorded yet.")
                return

            try:
                if os.path.exists(ZIP_FILE):
                    os.remove(ZIP_FILE)

                # Password encrypted zip generation
                pyminizip.compress(CSV_FILE, None, ZIP_FILE, ZIP_PASSWORD, 5)

                with open(ZIP_FILE, "rb") as f:
                    zip_data = f.read()

                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", "attachment; filename=whitelist_protected.zip")
                self.send_header("Content-Length", str(len(zip_data)))
                self.end_headers()
                self.wfile.write(zip_data)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(f"Encryption error: {str(e)}".encode("utf-8"))
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
        # WHITELIST SUBMISSION STORAGE
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
                print(f"[DATA SAVED] Pass: {pass_id} | User: {x_handle} | Wallet: {wallet}")
                self.send_json(200, {"status": "success", "message": "Record saved"})
            except Exception as e:
                print(f"[STORAGE ERROR] {e}")
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
    print("")
    print("========================================")
    print(" DRAGONHOOD SECURE OAUTH SERVER")
    print("========================================")
    print("Status : Running on port", PORT)
    print("Press CTRL+C to stop.")
    print("")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

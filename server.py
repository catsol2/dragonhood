from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime
import json
import base64
import csv
import os

PORT = int(os.environ.get("PORT", 5500))
ROOT = os.path.dirname(os.path.abspath(__file__))

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
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

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
                self.send_json(200, {"status": "success", "message": "Record successfully stored"})
            except Exception as e:
                print(f"[STORAGE ERROR] {e}")
                self.send_json(500, {"error": "failed_to_save_data", "details": str(e)})
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
                    try:
                        result = json.loads(raw.decode("utf-8"))
                    except Exception:
                        result = {"error": "invalid_x_response", "raw": raw.decode("utf-8", errors="replace")}
                    self.send_json(response.status, result)
                return

            except HTTPError as error:
                raw = error.read()
                try:
                    result = json.loads(raw.decode("utf-8"))
                except Exception:
                    result = {"error": "x_token_http_error", "status": error.code, "raw": raw.decode("utf-8", errors="replace")}
                self.send_json(error.code, result)
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
                    try:
                        result = json.loads(raw.decode("utf-8"))
                    except Exception:
                        result = {"error": "invalid_x_me_response", "raw": raw.decode("utf-8", errors="replace")}
                    self.send_json(response.status, result)
                return

            except HTTPError as error:
                raw = error.read()
                try:
                    result = json.loads(raw.decode("utf-8"))
                except Exception:
                    result = {"error": "x_me_http_error", "status": error.code, "raw": raw.decode("utf-8", errors="replace")}
                self.send_json(error.code, result)
                return

            except URLError as error:
                self.send_json(502, {"error": "x_me_network_error", "details": str(error)})
                return

            except Exception as error:
                self.send_json(500, {"error": "x_me_server_error", "details": str(error)})
                return

        if path.startswith("/api/"):
            self.send_json(404, {"error": "api_route_not_found", "path": path})
            return

        self.send_error(404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

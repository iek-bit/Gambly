"""Simple HTTP server to handle session logout requests."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
from storage import release_account_session


class LogoutHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/logout":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))
                
                account = data.get("account")
                session_id = data.get("session_id")
                
                if account and session_id:
                    release_account_session(account, session_id)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress logging
        pass


def start_logout_server():
    """Start the logout handler server in a background thread."""
    server = HTTPServer(("localhost", 8502), LogoutHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    server = start_logout_server()
    print("Logout server running on http://localhost:8502")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

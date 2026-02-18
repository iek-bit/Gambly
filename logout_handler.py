"""Simple HTTP server to handle session logout requests."""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
from storage import auto_remove_blackjack_lan_player, release_account_session


class LogoutHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/logout":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))
                
                account = data.get("account")
                session_id = data.get("session_id")
                accounts = data.get("accounts")
                lan_players = data.get("lan_players")
                
                if account and session_id:
                    release_account_session(account, session_id)
                    auto_remove_blackjack_lan_player(account)
                if isinstance(accounts, list):
                    for entry in accounts:
                        if not isinstance(entry, dict):
                            continue
                        entry_account = entry.get("account")
                        entry_session_id = entry.get("session_id")
                        if entry_account and entry_session_id:
                            release_account_session(entry_account, entry_session_id)
                            auto_remove_blackjack_lan_player(entry_account)
                if isinstance(lan_players, list):
                    for player_name in lan_players:
                        if not player_name:
                            continue
                        auto_remove_blackjack_lan_player(player_name)
                
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

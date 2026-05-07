from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from datetime import datetime
import socket

class PingTimeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            
        elif self.path == '/time':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            current_time = datetime.utcnow().isoformat() + 'Z'
            response = json.dumps({
                'time': current_time,
                'service': 'ping-time-server'
            })
            self.wfile.write(response.encode())
            
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

    def log_message(self, format, *args):
        # Customize logging to show requests in console
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.address_string()} - {format % args}")

if __name__ == '__main__':
    port = 8000
    server = HTTPServer(('0.0.0.0', port), PingTimeHandler)
    print(f"Server running on port {port}...")
    print("Endpoints:")
    print("  GET /ping -> 200 OK")
    print("  GET /time -> {\"time\": ISO8601, \"service\": \"ping-time-server\"}")
    server.serve_forever()
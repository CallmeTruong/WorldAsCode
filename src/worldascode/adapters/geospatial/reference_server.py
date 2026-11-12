"""Loopback SDK reference service; no dependency on the research application."""

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from worldascode.config import RESOURCE_ROOT, Settings, paths


def create_server(longitude, latitude, token, port=8767):
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("INVALID_REFERENCE_COORDINATES")

    class ReferenceHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.headers.get("Host") not in {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }:
                self.send_error(403)
                return
            route = unquote(urlparse(self.path).path)
            if route == "/config":
                if not token:
                    self.send_error(503, "Cesium token not configured")
                    return
                payload = json.dumps(
                    {
                        "ionToken": token,
                        "longitude": longitude,
                        "latitude": latitude,
                        "target_height": 15,
                    }
                ).encode()
                mime = "application/json"
            else:
                if route.startswith("/cesium/"):
                    base = (paths().node_modules / "cesium/Build/Cesium").resolve()
                    target = (base / route[len("/cesium/") :]).resolve()
                else:
                    base = RESOURCE_ROOT / "geospatial"
                    name = {
                        "/": "google-reference.html",
                        "/google-reference.js": "google-reference.js",
                    }.get(route)
                    if name is None:
                        self.send_error(404)
                        return
                    target = base / name
                if not target.is_relative_to(base) or not target.is_file():
                    self.send_error(404)
                    return
                payload = target.read_bytes()
                mime = (
                    "application/javascript"
                    if target.suffix == ".js"
                    else mimetypes.guess_type(target.name)[0]
                    or "application/octet-stream"
                )
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer(("127.0.0.1", port), ReferenceHandler)


def serve_reference(longitude, latitude, port=8767):
    import os

    Settings.load()
    token = next(
        (
            value
            for key, value in os.environ.items()
            if key.upper() == "CESIUM_ION_TOKEN"
        ),
        None,
    )
    if not token:
        raise ValueError("CESIUM_ION_TOKEN_REQUIRED")
    with create_server(longitude, latitude, token, port) as server:
        print(f"Reference viewer: http://127.0.0.1:{server.server_port}/", flush=True)
        server.serve_forever()

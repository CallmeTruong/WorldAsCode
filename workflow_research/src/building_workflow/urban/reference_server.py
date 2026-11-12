"""Local SDK viewer; only the Cesium client token is supplied transiently, never saved."""
import argparse
import json
from functools import partial
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,unquote
from dotenv import dotenv_values
from ..config import ROOT


class ReferenceHandler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):pass

    def do_GET(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
            self.send_error(403);return
        path=unquote(urlparse(self.path).path)
        if path=='/config':
            values=dotenv_values(ROOT.parent/'.env');token=next((v for k,v in values.items() if k.upper()=='CESIUM_ION_TOKEN'),None)
            if not token:self.send_error(503,'Cesium token missing');return
            payload=json.dumps({'ionToken':token,**self.server.aoi}).encode();mime='application/json'
        else:
            if path.startswith('/cesium/'):
                base=(ROOT/'node_modules/cesium/Build/Cesium').resolve();file=(base/path[len('/cesium/'):]).resolve()
            else:
                base=(ROOT/'runtime').resolve();name={'/':'google-reference.html','/google-reference.js':'google-reference.js'}.get(path)
                if name is None:self.send_error(404);return
                file=base/name
            if not file.is_relative_to(base) or not file.is_file():self.send_error(404);return
            payload=file.read_bytes()
            import mimetypes
            mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
            if file.suffix=='.js':mime='application/javascript'
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload)


def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8766);p.add_argument('--longitude',type=float,default=106.7032);p.add_argument('--latitude',type=float,default=10.7763)
    args=p.parse_args();server=ThreadingHTTPServer(('127.0.0.1',args.port),ReferenceHandler)
    server.aoi={'longitude':args.longitude,'latitude':args.latitude,'target_height':15}
    print('Local Google reference viewer: http://127.0.0.1:'+str(args.port),flush=True)
    server.serve_forever()


if __name__=='__main__':main()

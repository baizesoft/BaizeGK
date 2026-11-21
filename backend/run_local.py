"""Serve the built UI and API on Windows loopback with an explicit local database."""
import argparse
import os
from pathlib import Path
import re

import uvicorn
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles


def main():
    parser = argparse.ArgumentParser(description='启动白泽公考（仅本机访问）')
    parser.add_argument('--db', type=Path, default=Path('C:/data/BaizeGK/study.sqlite3'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('端口必须在 1024–65535')
    backend = Path(__file__).resolve().parent
    dist = backend.parent / 'frontend' / 'dist'
    db = args.db.resolve()
    if not (dist / 'index.html').is_file() or not (dist / 'assets').is_dir():
        parser.error('请先在 frontend 执行 npm ci / npm run build')
    db.parent.mkdir(parents=True, exist_ok=True)
    os.environ['BAIZEGK_DB_FILE'] = str(db)

    from app.main import app

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])

    @app.middleware('http')
    async def same_origin_writes(request: Request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin not in {
                f'http://127.0.0.1:{args.port}', f'http://localhost:{args.port}',
            }):
                return JSONResponse({'detail': '只允许本机同源写入'}, status_code=403)
        return await call_next(request)

    app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='ui-assets')
    if (dist / 'examples').is_dir():
        app.mount('/examples', StaticFiles(directory=dist / 'examples'), name='ui-examples')
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, 'path', None) != '/']

    @app.get('/', include_in_schema=False)
    @app.get('/{path:path}', include_in_schema=False)
    def serve(path: str = ''):
        if path == 'favicon.svg' and (dist / path).is_file():
            return FileResponse(dist / path)
        if re.fullmatch(r'(?:quiz|papers|materials|(?:study|jobs)/(?:gz-tr|cq))?', path):
            return FileResponse(dist / 'index.html', headers={'Cache-Control': 'no-cache'})
        return JSONResponse({'detail': 'Not Found'}, status_code=404)

    print(f'白泽公考：http://127.0.0.1:{args.port}/ · 本地数据：{db}', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()

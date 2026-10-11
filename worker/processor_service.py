"""Bounded internal document service, deployed without DB credentials or storage mounts."""
from pathlib import Path
import asyncio
import hmac
import os
import signal
import subprocess
import sys
import tempfile

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from .config import secret

ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT = 20 * 1024**2
MAX_OUTPUT = 4 * 1024**2
slots = asyncio.Semaphore(1)


def parser_environment():
    allowed = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL', 'TESSERACT_CMD', 'OLLAMA_URL', 'OLLAMA_MODEL', 'FSP_REQUIRE_GPU', 'FSP_GPU_MIN_OFFLOAD_PERCENT', 'FSP_OLLAMA_KEEP_ALIVE', 'PYTHONUTF8', 'OMP_THREAD_LIMIT')
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env['PYTHONUTF8'] = '1'
    return env


async def process(request: Request):
    token = secret('PROCESSOR_TOKEN', '')
    supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
    if len(token) < 32 or not hmac.compare_digest(supplied.encode(), token.encode()):
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    kind = request.headers.get('x-document-kind', '')
    if kind not in ('resume', 'vacancy', 'profile_export', 'employment', 'employment_compare', 'qualification_generate'):
        return JSONResponse({'error': 'invalid_kind'}, status_code=400)
    if slots.locked():
        return JSONResponse({'error': 'processor_busy'}, status_code=503, headers={'Retry-After': '10'})
    async with slots:
        async def receive():
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_INPUT:
                    raise ValueError('size_limit')
                data.extend(chunk)
            return data
        try:
            data = await asyncio.wait_for(receive(), timeout=30)
        except (ValueError, TimeoutError):
            return JSONResponse({'error': 'input_limit'}, status_code=413)
        if kind in ('profile_export', 'employment_compare', 'qualification_generate'):
            extension = 'json'
            if len(data) > 100_000:
                return JSONResponse({'error': 'profile_limit'}, status_code=413)
        elif data.startswith(b'%PDF-'):
            extension = 'pdf'
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):
            extension = 'png'
        elif data.startswith(b'\xff\xd8\xff'):
            extension = 'jpg'
        else:
            return JSONResponse({'error': 'unsupported_file'}, status_code=415)
        with tempfile.TemporaryDirectory(prefix='fsp-parse-') as temporary:
            directory = Path(temporary)
            (directory / f'input.{extension}').write_bytes(data)
            child = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'worker.parser_child', str(directory), kind,
                cwd=ROOT, env=parser_environment(), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                start_new_session=os.name != 'nt',
            )
            try:
                await asyncio.wait_for(child.wait(), timeout=280)
                output = directory / ('result.pdf' if kind == 'profile_export' else 'result.json')
                if child.returncode or not output.is_file() or output.stat().st_size > MAX_OUTPUT:
                    return JSONResponse({'error': 'invalid_document'}, status_code=422)
                return Response(output.read_bytes(), media_type='application/pdf' if kind == 'profile_export' else 'application/json')
            except TimeoutError:
                return JSONResponse({'error':'processing_timeout'},status_code=504)
            finally:
                if child.returncode is None:
                    if os.name != 'nt':
                        os.killpg(child.pid, signal.SIGKILL)
                    else:
                        child.kill()
                    await child.wait()


async def health(_):
    return JSONResponse({'status': 'ok'})


async def ready(request):
    token=secret('PROCESSOR_TOKEN','')
    supplied=request.headers.get('authorization','').removeprefix('Bearer ')
    if len(token)<32 or not hmac.compare_digest(supplied.encode(),token.encode()):
        return JSONResponse({'error':'unauthorized'},status_code=401)
    return JSONResponse({'status':'busy' if slots.locked() else 'ready'},status_code=503 if slots.locked() else 200)


app = Starlette(routes=[Route('/health', health), Route('/ready', ready), Route('/process', process, methods=['POST'])])


if __name__ == '__main__':
    import uvicorn
    if len(secret('PROCESSOR_TOKEN', '')) < 32:
        raise SystemExit('A private PROCESSOR_TOKEN of at least 32 characters is required')
    if any(key in os.environ for key in ('DATABASE_URL', 'DATABASE_URL_FILE', 'WORKER_DATABASE_URL', 'WORKER_DATABASE_URL_FILE', 'SMTP_PASSWORD', 'SMTP_PASSWORD_FILE', 'SMTP_USER')):
        raise SystemExit('Processor must not inherit database or SMTP credentials')
    uvicorn.run(app, host=os.getenv('PROCESSOR_BIND', '127.0.0.1'), port=8081,
                access_log=False, limit_concurrency=16, backlog=32, timeout_keep_alive=5,
                h11_max_incomplete_event_size=16384, timeout_graceful_shutdown=300)

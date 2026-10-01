"""Bound decoded HTTP body bytes, including chunked requests, before multipart parsing.

The server spools to a temporary file after 1 MiB; it never materializes a complete
restore archive in Python memory. This is a request-body limit, not a disk quota.
"""
from tempfile import SpooledTemporaryFile
from starlette.responses import JSONResponse
from storyboarder.media.files import MAX_FILE_BYTES


def request_limit(path):
    if path.endswith('/documents/upload'):
        return 21 * 1024 * 1024
    if path.endswith('/restore'):
        return 1024**3
    if path.endswith('/upload'):
        return MAX_FILE_BYTES + 1024*1024
    return 2*1024*1024


class RequestBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in ('GET', 'HEAD', 'OPTIONS'):
            await self.app(scope, receive, send)
            return
        maximum, total = request_limit(scope['path']), 0
        with SpooledTemporaryFile(max_size=1024*1024, mode='w+b') as staged:
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body = message.get('body', b'')
                total += len(body)
                if total > maximum:
                    response = JSONResponse({'error': {'code': 'too_large', 'message': 'Request exceeds the configured size limit.'}}, status_code=413)
                    await response(scope, receive, send)
                    return
                staged.write(body)
                if not message.get('more_body', False):
                    break
            staged.seek(0)
            remaining = total
            completed = False

            async def replay():
                nonlocal remaining, completed
                if completed:
                    return await receive()
                body = staged.read(64*1024)
                remaining -= len(body)
                completed = remaining == 0
                return {'type': 'http.request', 'body': body, 'more_body': not completed}

            await self.app(scope, replay, send)

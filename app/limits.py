from starlette.responses import JSONResponse


class BodyLimit:
    """Bound incoming bodies before JSON parsing, including chunked requests."""
    def __init__(self, app, maximum=65536):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] in ('GET', 'HEAD', 'OPTIONS'):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.maximum:
                return await JSONResponse({'detail': 'Слишком большой запрос'}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body', False):
                break
        position = 0
        async def bounded_receive():
            nonlocal position
            if position < len(chunks):
                result = chunks[position]
                position += 1
                return result
            return await receive()
        await self.app(scope, bounded_receive, send)

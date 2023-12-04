"""µHTTP - ASGI micro framework"""

import json
import re
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs, unquote


MAX_REQUEST_BODY_LENGTH = 1024


class Response:
    def __init__(self, status, headers=None, cookies=None, body=b''):
        self.status = status
        self.headers = headers or {}
        self.headers.setdefault('content-type', 'text/html; charset=utf-8')
        self.cookies = SimpleCookie(cookies or {})
        self.body = body


class HTTPException(Exception):
    def __init__(self, status, body=''):
        self.status = status
        self.body = body or HTTPStatus(status).phrase


class App:
    def __init__(
        self,
        routes=None,
        startup=None,
        shutdown=None,
        before=None,
        after=None
    ):
        self.routes = routes or {}
        self._startup = startup or []
        self._shutdown = shutdown or []
        self._before = before or []
        self._after = after or []

    def startup(self, func):
        self._startup.append(func)
        return func

    def shutdown(self, func):
        self._shutdown.append(func)
        return func

    def before(self, func):
        self._before.append(func)
        return func

    def after(self, func):
        self._after.append(func)
        return func

    def route(self, path, methods=('GET',)):
        def decorator(func):
            self.routes[path] = {method: func for method in methods}
            return func
        return decorator

    async def mount(self, app, prefix=''):
        self._startup += app._startup
        self._shutdown += app._shutdown
        self._before += app._before
        self._after += app._after
        self.routes.update({prefix + k: v for k, v in app.routes.items()})

    async def __call__(self, scope, receive, send):
        class Request:
            pass

        if scope['type'] == 'lifespan':
            while True:
                event = await receive()
                if event['type'] == 'lifespan.startup':
                    try:
                        for func in self._startup:
                            await func(scope['state'])
                    except Exception as e:
                        await send({
                            'type': 'lifespan.startup.failed',
                            'message': f'{type(e).__name__}: {e}'
                        })
                        break
                    await send({'type': 'lifespan.startup.complete'})
                elif event['type'] == 'lifespan.shutdown':
                    try:
                        for func in self._shutdown:
                            await func(scope['state'])
                    except Exception as e:
                        await send({
                            'type': 'lifespan.shutdown.failed',
                            'message': f'{type(e).__name__}: {e}'
                        })
                        break
                    await send({'type': 'lifespan.shutdown.complete'})
                    break

        elif scope['type'] == 'http':
            request = Request()
            request.method = scope['method']
            request.path = scope['path']
            request.params = {}
            request.args = {
                k: v[0] for k, v in
                parse_qs(unquote(scope['query_string'])).items()
            }
            request.headers = {
                unquote(k): unquote(v) for k, v in scope['headers']
            }
            request.cookies = SimpleCookie()
            try:
                request.cookies.load(request.headers.get('cookie', ''))
            except CookieError:
                pass
            request.state = scope['state'].copy()
            request.body = b''
            request.json = {}
            request.form = {}

            try:
                while True:
                    event = await receive()
                    request.body += event['body']
                    if not event['more_body']:
                        break
                    if len(request.body) > MAX_REQUEST_BODY_LENGTH:
                        raise HTTPException(413)
                content_type = request.headers.get('content-type', '')
                if 'application/json' in content_type:
                    try:
                        request.json = json.loads(unquote(request.body))
                    except json.JSONDecodeError:
                        pass
                elif 'application/x-www-form-urlencoded' in content_type:
                    request.form = {
                        k: v[0] for k, v in
                        parse_qs(unquote(request.body)).items()
                    }
                for func in self._before:
                    await func(request)

                for route, methods in self.routes.items():
                    if matches := re.fullmatch(route, request.path):
                        request.params = matches.groupdict()
                        if func := methods.get(request.method):
                            ret = await func(request)
                            break
                        raise HTTPException(405)
                else:
                    raise HTTPException(404)

                if type(ret) is int:
                    raise HTTPException(ret)
                elif type(ret) is str:
                    response = Response(200, body=ret.encode())
                elif type(ret) is bytes:
                    response = Response(200, body=ret)
                elif type(ret) is dict:
                    response = Response(
                        status=200,
                        headers={'content-type': 'application/json'},
                        body=json.dumps(ret).encode()
                    )
                elif type(ret) is Response:
                    response = ret
                elif ret is None:
                    response = Response(204)
                else:
                    raise ValueError('Invalid response type')

            except HTTPException as e:
                response = Response(status=e.status, body=e.body.encode())
            for func in self._after:
                await func(request, response)
            response.headers['content-length'] = len(response.body)

            await send({
                'type': 'http.response.start',
                'status': response.status,
                'headers': [
                    [str(k).lower().encode(), str(v).encode()]
                    for k, v in response.headers.items()
                ] + [
                    [k.lower().encode(), v.encode()] for k, v in (
                        header.split(': ', maxsplit=1) for header in
                        response.cookies.output().splitlines()
                    )
                ]
            })
            await send({
                'type': 'http.response.body',
                'body': response.body
            })
        else:
            raise NotImplementedError(scope['type'], 'is not supported')

"""µHTTP - ASGI micro framework"""

import json
import re
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs


MAX_REQUEST_BODY_LENGTH = 1024


class HTTPException(Exception):
    def __init__(self, status, body=''):
        self.status = status
        self.body = body or HTTPStatus(status).phrase


class Request:
    def __init__(
        self,
        *,
        method,
        path,
        params=None,
        args=None,
        headers=None,
        body='',
        state=None
    ):
        self.method = method
        self.path = path
        self.params = params or {}
        self.args = args or {}
        self.headers = headers or {}
        self.cookies = SimpleCookie()
        try:
            self.cookies.load(self.headers.get('cookie', ''))
        except CookieError:
            pass
        self.body = body
        self.form = {k: v[0] for k, v in parse_qs(self.body).items()}
        self.json = {}
        try:
            self.json = json.loads(self.body)
        except json.JSONDecodeError:
            pass
        self.state = state or {}


class Response:
    def __init__(self, *, status, headers=None, cookies=None, body=''):
        self.status = status
        self.headers = headers or {}
        self.headers.setdefault('content-type', 'text/html; charset=utf-8')
        self.cookies = SimpleCookie(cookies or {})
        self.body = body


class App:
    def __init__(
        self,
        routes=None,
        *,
        startup=None,
        shutdown=None,
        before_response=None,
        after_response=None
    ):
        self.routes = routes or {}
        self._startup = startup or []
        self._shutdown = shutdown or []
        self._before_response = before_response or []
        self._after_response = after_response or []

    def startup(self, func):
        self._startup.append(func)
        return func

    def shutdown(self, func):
        self._shutdown.append(func)
        return func

    def before_response(self, func):
        self._before_response.append(func)
        return func

    def after_response(self, func):
        self._after_response.append(func)
        return func

    def route(self, path, methods=('GET',)):
        def decorator(func):
            self.routes[path] = {method: func for method in methods}
            return func
        return decorator

    async def __call__(self, scope, receive, send):
        match scope['type']:
            case 'lifespan':
                while True:
                    event = await receive()
                    match event['type']:
                        case 'lifespan.startup':
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
                        case 'lifespan.shutdown':
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
            case 'http':
                try:
                    request_body = b''
                    while True:
                        event = await receive()
                        request_body += event['body']
                        if not event['more_body']:
                            break
                        if len(request_body) > MAX_REQUEST_BODY_LENGTH:
                            raise HTTPException(413)
                    request = Request(
                        method=scope['method'],
                        path=scope['path'],
                        args={
                            k: v[0] for k, v in
                            parse_qs(scope['query_string'].decode()).items()
                        },
                        headers={
                            k.decode(): v.decode() for k, v in scope['headers']
                        },
                        body=request_body.decode(),
                        state=scope['state'].copy()
                    )
                    for func in self._before_response:
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
                    match ret:
                        case str():
                            response = Response(status=200, body=ret)
                        case dict():
                            response = Response(
                                status=200,
                                headers={'content-type': 'application/json'},
                                body=json.dumps(ret)
                            )
                        case Response():
                            response = ret
                        case _:
                            raise ValueError('Invalid response type')
                except HTTPException as e:
                    response = Response(**e.__dict__)
                for func in self._after_response:
                    await func(request, response)
                body = response.body.encode()
                response.headers['content-length'] = len(body)
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
                await send({'type': 'http.response.body', 'body': body})
            case other:
                raise NotImplementedError(other, 'is not supported')

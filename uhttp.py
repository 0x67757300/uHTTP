"""µHTTP - ASGI micro framework"""

import re
import json
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs, unquote
from asyncio import to_thread
from inspect import iscoroutinefunction


class Request:
    def __init__(
        self,
        method,
        path,
        *,
        params=None,
        args=None,
        headers=None,
        cookies=None,
        body=b'',
        json=None,
        form=None,
        state=None
    ):
        self.method = method
        self.path = path
        self.params = params or {}
        self.args = args or {}
        self.headers = headers or {}
        self.cookies = SimpleCookie(cookies)
        self.body = body
        self.json = json or {}
        self.form = form or {}
        self.state = state or {}


class Response(Exception):
    def __init__(self, status, *, headers=None, cookies=None, body=b''):
        self.status = status
        try:
            self.description = HTTPStatus(status).phrase
        except ValueError:
            self.description = ''
        super().__init__(self.description)
        self.headers = headers or {}
        self.headers.setdefault('content-type', 'text/html; charset=utf-8')
        self.cookies = SimpleCookie(cookies)
        self.body = body
        if not self.body and (status >= 400 and status < 600):
            self.body = str(self).encode()


class App:
    def __init__(
        self,
        *,
        routes=None,
        startup=None,
        shutdown=None,
        before=None,
        after=None,
        max_content=1048576
    ):
        self._routes = routes or {}
        self._startup = startup or []
        self._shutdown = shutdown or []
        self._before = before or []
        self._after = after or []
        self._max_content = max_content

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
            self._routes.setdefault(path, {}).update({
                method: func for method in methods
            })
            return func
        return decorator

    def get(self, path):
        return self.route(path, methods=('GET',))

    def head(self, path):
        return self.route(path, methods=('HEAD',))

    def post(self, path):
        return self.route(path, methods=('POST',))

    def put(self, path):
        return self.route(path, methods=('PUT',))

    def delete(self, path):
        return self.route(path, methods=('DELETE',))

    def connect(self, path):
        return self.route(path, methods=('CONNECT',))

    def options(self, path):
        return self.route(path, methods=('OPTIONS',))

    def trace(self, path):
        return self.route(path, methods=('TRACE',))

    def patch(self, path):
        return self.route(path, methods=('PATCH',))

    async def mount(self, app, prefix=''):
        self._startup += app._startup
        self._shutdown += app._shutdown
        self._before += app._before
        self._after += app._after
        self._routes.update({prefix + k: v for k, v in app._routes.items()})
        self._max_content = max(self._max_content, app._max_content)

    @staticmethod
    async def asyncfy(func, /, *args, **kwargs):
        if iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return await to_thread(func, *args, **kwargs)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                event = await receive()
                if event['type'] == 'lifespan.startup':
                    try:
                        for func in self._startup:
                            await self.asyncfy(func, scope['state'])
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
                            await self.asyncfy(func, scope['state'])
                    except Exception as e:
                        await send({
                            'type': 'lifespan.shutdown.failed',
                            'message': f'{type(e).__name__}: {e}'
                        })
                        break
                    await send({'type': 'lifespan.shutdown.complete'})
                    break
        elif scope['type'] == 'http':
            request = Request(
                method=scope['method'],
                path=scope['path'],
                args={
                    k: v[0] for k, v in
                    parse_qs(unquote(scope['query_string'])).items()
                },
                headers={unquote(k): unquote(v) for k, v in scope['headers']},
                state=scope['state'].copy()
            )
            try:
                request.cookies.load(request.headers.get('cookie', ''))
            except CookieError:
                pass
            try:
                while True:
                    event = await receive()
                    request.body += event['body']
                    if len(request.body) > self._max_content:
                        raise Response(413)
                    if not event['more_body']:
                        break
                content_type = request.headers.get('content-type', '')
                if 'application/json' in content_type:
                    try:
                        request.json = await to_thread(
                            json.loads, request.body.decode(errors='replace')
                        )
                    except json.JSONDecodeError:
                        pass
                elif 'application/x-www-form-urlencoded' in content_type:
                    request.form = {
                        k: v[0] for k, v in
                        (
                            await to_thread(parse_qs, unquote(request.body))
                        ).items()
                    }
                for func in self._before:
                    await self.asyncfy(func, request)
                for route, methods in self._routes.items():
                    if matches := re.fullmatch(route, request.path):
                        request.params = matches.groupdict()
                        if func := methods.get(request.method):
                            ret = await self.asyncfy(func, request)
                            break
                        raise Response(405)
                else:
                    raise Response(404)
                if isinstance(ret, int):
                    raise Response(ret)
                elif isinstance(ret, str):
                    response = Response(200, body=ret.encode())
                elif isinstance(ret, bytes):
                    response = Response(200, body=ret)
                elif isinstance(ret, dict):
                    response = Response(
                        status=200,
                        headers={'content-type': 'application/json'},
                        body=json.dumps(ret).encode()
                    )
                elif isinstance(ret, Response):
                    response = ret
                elif ret is None:
                    response = Response(204)
                else:
                    raise ValueError('Invalid response type')
            except Response as early_response:
                response = early_response
            for func in self._after:
                await self.asyncfy(func, request, response)
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

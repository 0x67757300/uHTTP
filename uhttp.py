"""µHTTP - Pythonic web development"""

import re
import json
from http import HTTPStatus
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs, unquote
from asyncio import to_thread
from inspect import iscoroutinefunction
from typing import Any, Callable, Iterable, Optional, Union


class App:
    """An ASGI application.

    Called once per request by the ASGI server.

    Currently, doesn't support the WebSocket protocol. However, adding
    support is easy:

    ```python
    _app = App()

    async def app(scope, receive, send):
        if scope['type'] == 'websocket':
            pass  # WebSocket code goes here
        else:
            await _app(scope, receive, send)
    ```
    """

    def __init__(
        self,
        *,
        routes: Optional[
            dict[str, dict[str, Callable[['Request'], Any]]]
        ] = None,
        startup: Optional[list[Callable[[dict], Any]]] = None,
        shutdown: Optional[list[Callable[[dict], Any]]] = None,
        before: Optional[list[Callable[['Request'], Any]]] = None,
        after: Optional[list[Callable[['Request', 'Response'], Any]]] = None,
        max_content: int = 1048576
    ):
        """Initializes an App.

        E.g.:

        ```python
        app = App(
            startup=[open_db],
            before=[counter, auth],
            routes={
                '/': {
                    'GET': lambda request: 'HI!',
                    'POST': new
                },
                '/users/': {
                    'GET': users,
                    'PUT': users
                }
            },
            after=[logger],
            shutdown=[close_db]
        )
        ```
        """
        self._routes = routes or {}
        self._startup = startup or []
        self._shutdown = shutdown or []
        self._before = before or []
        self._after = after or []
        self._max_content = max_content

    def mount(self, app: 'App', prefix: str = ''):
        """Mounts another app."""
        self._startup += app._startup
        self._shutdown += app._shutdown
        self._before += app._before
        self._after += app._after
        self._routes.update({prefix + k: v for k, v in app._routes.items()})
        self._max_content = max(self._max_content, app._max_content)

    def startup(self, func: Callable[[dict], Any]):
        """A startup decorator.

        Appends the decorated function to the list of startup functions.
        These functions are called at the beginning of the Lifespan
        protocol (when you start the server) with the state argument. A
        shallow copy of state is passed to each request.

        E.g.:

        ```python
        @app.startup
        def open_db(state):
            state['db'] = {}
        ```
        """
        self._startup.append(func)
        return func

    def shutdown(self, func: Callable[[dict], Any]):
        """A shutdown decorator.

        Appends the decorated function to the list of shutdown
        functions. These functions are called at the end of the Lifespan
        protocol (when you stop the server) with the state argument.

        E.g.:

        ```python
        @app.shutdown
        def close_db(state):
            del state['db']
        ```
        """
        self._shutdown.append(func)
        return func

    def before(self, func: Callable[['Request'], Any]):
        """A before decorator.

        Appends the decorated function to the list of before functions.
        These functions are called before a response is made with a
        request argument. In particular, `request.params` might be empty
        at this point.

        E.g.:

        ```python
        @app.before
        def auth(request):
            if 'john' not in request.state['db']:
                raise Response(401)
        ```
        """
        self._before.append(func)
        return func

    def after(self, func: Callable[['Request', 'Response'], Any]):
        """An after decorator.

        Appends the decorated function to the list of after functions.
        These functions are called after a response is made with
        request and response arguments.

        E.g.:

        ```python
        @app.after
        def logger(request, response):
            print(request, '-->', response)
        ```
        """
        self._after.append(func)
        return func

    def route(self, path: str, methods: Iterable[str] = ('GET',)):
        """A route decorator.

        Adds the decorated function to the routing table.

        The path is treated as a regular expression. To get request
        parameters (e.g. `/user/<id>`) you should use named groups. All
        paths are compiled at the startup for performance reasons.

        If the request path doesn't match a `404 Not Found` response is
        returned.

        If the request method isn't in methods a `405 Method Not
        Allowed` response is returned.

        E.g.:

        ```python
        @app.route('/', methods=('GET', 'POST'))
        def index(request):
            return f'{request.method}ing from {request.client.ip}'
        ```
        """
        def decorator(func):
            self._routes.setdefault(path, {}).update({
                method: func for method in methods
            })
            return func
        return decorator

    def get(self, path: str):
        """A `GET` route."""
        return self.route(path, methods=('GET',))

    def head(self, path: str):
        """A `HEAD` route."""
        return self.route(path, methods=('HEAD',))

    def post(self, path: str):
        """A `POST` route."""
        return self.route(path, methods=('POST',))

    def put(self, path: str):
        """A `PUT` route."""
        return self.route(path, methods=('PUT',))

    def delete(self, path: str):
        """A `DELETE` route."""
        return self.route(path, methods=('DELETE',))

    def connect(self, path: str):
        """A `CONNECT` route."""
        return self.route(path, methods=('CONNECT',))

    def options(self, path: str):
        """An `OPTIONS` route."""
        return self.route(path, methods=('OPTIONS',))

    def trace(self, path: str):
        """A `TRACE` route."""
        return self.route(path, methods=('TRACE',))

    def patch(self, path: str):
        """A `PATCH` route."""
        return self.route(path, methods=('PATCH',))

    async def __call__(self, scope: dict, receive: Callable, send: Callable):
        state = scope.get('state', {})

        if scope['type'] == 'lifespan':
            while True:
                event = await receive()

                if event['type'] == 'lifespan.startup':
                    try:
                        for func in self._startup:
                            await asyncfy(func, state)
                        self._routes = {
                            re.compile(k): v for k, v in self._routes.items()
                        }
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
                            await asyncfy(func, state)
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
                args=parse_qs(unquote(scope['query_string'])),
                state=state.copy()
            )

            try:
                try:
                    request.headers = MultiDict([
                        [k.decode(), v.decode()] for k, v in scope['headers']
                    ])
                except UnicodeDecodeError:
                    raise Response(400)

                try:
                    request.cookies.load(request.headers.get('cookie', ''))
                except CookieError:
                    raise Response(400)

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
                            json.loads, request.body.decode()
                        )
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise Response(400)
                elif 'application/x-www-form-urlencoded' in content_type:
                    request.form = MultiDict(await to_thread(
                        parse_qs, unquote(request.body)
                    ))

                for func in self._before:
                    if ret := await asyncfy(func, request):
                        raise Response.from_any(ret)

                for route, methods in self._routes.items():
                    if matches := route.fullmatch(request.path):
                        request.params = matches.groupdict()
                        if func := methods.get(request.method):
                            ret = await asyncfy(func, request)
                            response = Response.from_any(ret)
                        else:
                            response = Response(405)
                            response.headers['allow'] = ', '.join(methods)
                        break
                else:
                    response = Response(404)

            except Response as early_response:
                response = early_response

            try:
                for func in self._after:
                    if ret := await asyncfy(func, request, response):
                        raise Response.from_any(ret)
            except Response as early_response:
                response = early_response

            response.headers._update({'content-length': [len(response.body)]})
            if response.cookies:
                response.headers._update({
                    'set-cookie': [
                        header.split(': ', maxsplit=1)[1]
                        for header in response.cookies.output().splitlines()
                    ]
                })

            await send({
                'type': 'http.response.start',
                'status': response.status,
                'headers': [
                    [str(k).lower().encode(), str(v).encode()]
                    for k, l in response.headers._items() for v in l
                ]
            })
            await send({
                'type': 'http.response.body',
                'body': response.body
            })

        else:
            raise NotImplementedError(scope['type'], 'is not supported')


class Request:
    """A HTTP request."""
    method: str
    path: str
    params: dict[str, str]
    args: 'MultiDict'
    headers: 'MultiDict'
    cookies: SimpleCookie
    body: bytes
    json: Any
    form: 'MultiDict'
    state: dict

    def __init__(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        args: Optional[Union['MultiDict', dict, list]] = None,
        headers: Optional[Union['MultiDict', dict, list]] = None,
        cookies: Optional[dict] = None,
        body: bytes = b'',
        json: Optional[Any] = None,
        form: Optional[Union['MultiDict', dict, list]] = None,
        state: Optional[dict] = None
    ):
        self.method = method
        self.path = path
        self.params = params or {}
        self.args = MultiDict(args)
        self.headers = MultiDict(headers)
        self.cookies = SimpleCookie(cookies)
        self.body = body
        self.json = json
        self.form = MultiDict(form)
        self.state = state or {}

    def __repr__(self):
        return f'{self.method} {self.path}'


class Response(Exception):
    """A HTTP Response.

    They can be raised at any point for the early response pattern.

    E.g.

    ```python
    def user(db, user):
        if user in db:
            return db.get(user)
        else:
            raise Response(401)

    @app.get('/account')
    def account(request):
        user = user(request.state['db'], 'john')
    ```
    """
    status: int
    description: str
    headers: 'MultiDict'
    cookies: SimpleCookie
    body: bytes

    def __init__(
        self,
        status: int,
        *,
        headers: Optional[Union['MultiDict', dict, list]] = None,
        cookies: Optional[dict] = None,
        body: bytes = b''
    ):
        self.status = status
        try:
            self.description = HTTPStatus(status).phrase
        except ValueError:
            self.description = ''
        super().__init__(self.description)
        self.headers = MultiDict(headers)
        self.headers.setdefault('content-type', 'text/html; charset=utf-8')
        self.cookies = SimpleCookie(cookies)
        self.body = body
        if not self.body and status in range(400, 600):
            self.body = str(self).encode()

    def __repr__(self):
        return f'{self.status} {self.description}'

    @classmethod
    def from_any(cls, any: Any) -> 'Response':
        if isinstance(any, int):
            return cls(status=any, body=HTTPStatus(any).phrase.encode())
        elif isinstance(any, str):
            return cls(status=200, body=any.encode())
        elif isinstance(any, bytes):
            return cls(status=200, body=any)
        elif isinstance(any, dict):
            return cls(
                status=200,
                headers={'content-type': 'application/json'},
                body=json.dumps(any).encode()
            )
        elif isinstance(any, cls):
            return any
        elif any is None:
            return cls(status=204)
        else:
            raise TypeError


async def asyncfy(func, /, *args, **kwargs):
    """Makes any function awaitable.

    All synchronous code runs in a separate thread, so as to not block
    the main loop. As long as your code is thread-safe, things should
    be fine. E.g. instead of opening one `sqlite3` connection at
    startup, consider opening one for every request or just using
    `aiosqlite`.
    """
    if iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return await to_thread(func, *args, **kwargs)


class MultiDict(dict):
    """A dictionary with multiple values for the same key."""
    def __init__(self, mapping=None):
        if mapping is None:
            super().__init__()
        elif isinstance(mapping, MultiDict):
            super().__init__({k.lower(): v[:] for k, v in mapping.itemslist()})
        elif isinstance(mapping, dict):
            super().__init__({
                k.lower(): [v] if not isinstance(v, list) else v[:]
                for k, v in mapping.items()
            })
        elif isinstance(mapping, (tuple, list)):
            super().__init__()
            for key, value in mapping:
                self._setdefault(key.lower(), []).append(value)
        else:
            raise TypeError('Invalid mapping type')

    def __getitem__(self, key):
        return super().__getitem__(key.lower())[-1]

    def __setitem__(self, key, value):
        super().setdefault(key.lower(), []).append(value)

    def _get(self, key, default=(None,)):
        return super().get(key.lower(), list(default))

    def get(self, key, default=None):
        return super().get(key.lower(), [default])[-1]

    def _items(self):
        return super().items()

    def items(self):
        return {k.lower(): v[-1] for k, v in super().items()}.items()

    def _pop(self, key, default=(None,)):
        return super().pop(key.lower(), list(default))

    def pop(self, key, default=None):
        values = super().get(key.lower(), [])
        if len(values) > 1:
            return values.pop()
        else:
            return super().pop(key.lower(), default)

    def _setdefault(self, key, default=(None,)):
        return super().setdefault(key.lower(), list(default))

    def setdefault(self, key, default=None):
        return super().setdefault(key.lower(), [default])[-1]

    def _values(self):
        return super().values()

    def values(self):
        return {k.lower(): v[-1] for k, v in super().items()}.values()

    def _update(self, *args, **kwargs):
        super().update(*args, **kwargs)

    def update(self, *args, **kwargs):
        new = {}
        new.update(*args, **kwargs)
        super().update(MultiDict(new))

# µHTTP 

Pythonic web development

µHTTP emerged from the need of a simple, hassle-free web framework. It's great for microservices, single page applications, AND monolithic monsters. 

In µHTTP there is no hidden logic. Everything is what it seems.

### Why

- Stupid simple, seriously there are maybe 15 lines of "real" code in it. No external dependencies.
- Extremely modular, entire extensions can just follow the simple App pattern.
- Flexible, say what you will about wrong responses, they work.
- Fast, because it doesn't really do much.
- **Very** opinionated, to the point where it has no opinions.
- Not typist.

### Installation

µHTTP is on [PyPI](https://pypi.org/project/uhttp/).

```bash
pip install uhttp
```

You might also need an [ASGI](https://asgi.readthedocs.io/en/latest/) server. I recommend [Uvicorn](https://www.uvicorn.org/).

```bash
pip install uvicorn
```

### Hello, world!

```python
#!/usr/bin/env python3

from uhttp import App


app = App()


@app.get('/')
def hello(request):
    return 'Hello, world!'


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('__main__:app')
```

### Inspirations

- [Flask](https://github.com/pallets/flask/): `from flask import *`
- [FastAPI](https://github.com/tiangolo/fastapi): `Union[Any, None]`
- [Sanic](https://github.com/sanic-org/sanic): A walking contradiction
- [Bottle](https://github.com/bottlepy/bottle): One file, 3500+ LOC
- [Django](https://github.com/django/django)

[The rant.](https://lobste.rs/s/ukh5id/uhttp_pythonic_web_development#c_9jln1d)

### TODO

- [ ] Tests
- [ ] Multipart requests
- [ ] Tutorial

## API Reference

### Application

```python
class App:
    _routes: dict
    _startup: list
    _shutdown: list
    _before: list
    _after: list
    _max_content: int

    def mount(self, app, prefix=''):
        self._startup += app._startup
        self._shutdown += app._shutdown
        self._before += app._before
        self._after += app._after
        self._routes.update({prefix + k: v for k, v in app._routes.items()})
        self._max_content = max(self._max_content, app._max_content)
```

In particular, this Django-like pattern is possible:

```python
app = App(
    startup=[open_db, dance],
    before=[auth],
    routes={
        '/': {
            'GET': index,
            'POST': filter
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

`app.mount` is µHTTP's modularity.

In `users.py` you have:
```python
from uhttp import App

app = App()

@app.before
def auth(request):
    ...

@app.route('/', methods=('GET', 'PUT'))
def users(request):
    ...
```

In `db.py`:
```python
from uhttp import App

app = App()

@app.startup
async def open_db(state):
    ...

@app.shutdown
async def close_db(state):
    ...
```

Finally, in `main.py`:

```python
from uhttp import App
import users
import db

app = App()
app.mount(users.app, prefix='/users')
app.mount(db.app)

@app.get('/')
def index(request):
    ...
```

Entire extensions can be just apps!

#### Lifespan functions

Lifespan functions are based on the [Lifespan Protocol](https://asgi.readthedocs.io/en/latest/specs/lifespan.html).

There are two decorators: `@app.startup` and `@app.shutdown`. Decorated functions receive one argument: `state`.

This is a great place to setup database connections and other dependencies that your application might need.

A shallow copy of the state is passed to each request.

#### Middleware

µHTTP provides two decorators `@app.before` and `@app.after`.

Any value returned from the decorated functions will set the response and break the control flow.

`@app.before` functions receive only a request argument. They are called before a response is made, i.e. before the route function (if there is one). Particularly, `request.params` is still empty at this point. This is a great place to handle bad requests. The early response pattern:

```python
from uhttp import App, Response

app = App()

@app.before
def auth(request):
    if 'user' not in requet.state:
        raise Response(401)
    if request.state['user']['credits'] < 1:
        return 402
```

`@app.after` functions receive a `request` and a `response`. They are called after a response is made. You should modify the response here.

```python
@app.after
def dancing(request, response):
    response.cookies['dancing'] = 'in the street'
    ...
```

#### Route functions

The main route decorator is `@app.route(path, methods=('GET',))`. There's also route decorators for all the standard methods: `@app.get, @app.head, @app.post, @app.put, @app.delete, @app.connect, @app.options, @app.trace, @app.patch`.

The `path` parameter is present on all decorators. µHTTP handles paths as regular expressions. To define path parameters like `/user/<id>` you can use named groups:

```python
@app.get('/users/(?P<id>\d+)')
def users(request):
    user_id = request.params['id']
    return {'user': request.state['db']['user_id']}
```

To improve performance, all path regular expressions are compiled at startup.

Route functions will only be called if no `@app.before` middleware has set the response.

The response comes from the return value of the decorated function. If there is no return, the response defaults to `204 No Content`. The return values can be: `int` (status), `str` (body), `bytes` (raw body), `dict` (JSON) and `Response`. 

If the request doesn't match any path, response is set to `404 Not Found`. If the request doesn't match any method of the path, response is set to `405 Method Not Allowed`.

#### Static files

µHTTP doesn't support static files. It shouldn't (a real web server like [Unit](https://unit.nginx.org/) should handle them). But in development they might come handy:

```python
import os
import mimetypes

@app.startup
def static(state):  # Non-recursive, keeps files in memory
    for entry in os.scandir('static'):
        if entry.is_file():
            with open(entry.path, 'rb') as f:
                content = f.read()
            content_type, _ = mimetypes.guess_type(entry.path)
            app._routes['/' + entry.path] = {
                    'GET': lambda _: Response(
                        status=200,
                        body=content,
                        headers={'content-type': content_type or ''}
                    )
                }
```

### Requests

```python
class Request:
    method: str
    path: str
    params: dict
    args: MultiDict
    cookies: SimpleCookie
    body: bytes
    json: Any
    form: MultiDict
    state: dict
```

#### Multipart requests

Currently, µHTTP doesn't support `multipart/form-data` requests. Here's an implementation with [`multipart`](https://pypi.org/project/multipart/):

```python
from io import BytesIO
from multipart import MultipartError, MultipartParser, parse_options_header

@app.before
def parse_multipart(request):
    content_type = request.headers.get('content-type', '')
    content_type, options = parse_options_header(content_type)
    content_length = int(request.headers.get('content-length', '-1'))
    if content_type == 'multipart/form-data':
        request.form['files'] = {}
        try:
            stream = BytesIO(request.body)
            boundary = options.get('boundary', '')
            if not boundary:
                raise MultipartError
            for part in MultipartParser(stream, boundary, content_length):
                if part.filename:
                    request.form['files'][part.name] = part.raw
                else:
                    request.form[part.name] = part.value
        except MultipartError:
            raise Response(400)
```

### Responses

```python
class Response(Exception):
    status: int
    description: str
    headers: MultiDict
    cookies: SimpleCookie
    body: bytes

    def from_any(any: Any) -> Response:
        ...
```

The fact that `Response` inherits from `Exception` is what makes µHTTP so flexible.

```python
def pay(request, cost):
    user = request.state.get('user')
    if not user:
        raise Response(401)
    if user.money < cost:
        raise Response(402, body=b'Insufficient funds!')
    user.money -= cost
    return user

@app.get('/buy/bananas')
def see_bananas(request):
    return "Hey there, see any bananas that you'd like?"

@app.post('/buy/bananas')
def buy_bananas(request):
    user = pay(request, 5)
    return f'Congratulations! {user.name} just bought a banana!'
```

#### Templates

µHTTP doesn't support templating engines. However, implementing [Jinja](https://jinja.palletsprojects.com/en/3.1.x/) is very easy:

```python
import jinja2

@app.startup
def load_jinja(state):
    state['jinja'] = jinja2.Environment(
        loader=jinja2.FileSystemLoader('templates')
    )


@app.route('/')
def hello(request):
    template = request.state['jinja'].get_template('hello.html')
    return template.render(name=request.args.get('name'))
```

### Internals

```python
async def asyncfy(func, /, *args, **kwargs):
    if iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return await to_thread(func, *args, **kwargs)
```

µHTTP runs all synchronous code in a separate thread, so as to not block the main loop. As long as your code is thread-safe things should be fine. E.g. instead of opening one `sqlite3` connection at startup, consider opening one for every request or just using [`aiosqlite`](https://github.com/omnilib/aiosqlite).

```python
class MultiDict(dict):
    ...
```

Because of HTTP 1.1 quirks, µHTTP has a MultiDict implementation. But, you shouldn't really care about that.

## Contributing

Feel free to fork, complain, improve, document, **write extensions**.

## License

Released under the MIT License.

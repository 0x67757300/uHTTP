# µHTTP 

Pythonic web development

## About

µHTTP emerged from the need of a simple, hassle-free web framework. It's great
for microservices, single page applications, AND monolithic monsters. 

In µHTTP there is no hidden logic. Everything is what it seems.

### Installation

µHTTP is on [PyPI](https://pypi.org/project/uhttp/).

```bash
pip install uhttp
```

You might also need a web server. µHTTP follows the
[ASGI](https://asgi.readthedocs.io/en/latest/) specification. A nice
implementation is [Uvicorn](https://www.uvicorn.org/).

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

## Reference

### Application

_In µHTTP everything is an app._

#### `class App`

The parameters are:

- `routes`: A `dict` of your routes, following: `{'/path': {'METHOD': func}}`
- `startup`: A `list` of functions that run at the beginning of the lifespan
- `shutdown`: A `list` of functions that run at the end of the lifespan
- `before`: A `list` of functions that run before the response
- `after`: A `list` of functions that run after the response
- `max_content`: An `int`, sets the request body size limit (defaults to 1 MB)

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

#### `app.mount(other_app, prefix='')`

`app.mount` is what makes µHTTP so fraking modular. Here's how:

1. Appends `other_app` middleware and lifespan functions to `app`
2. Maps `other_app` routes to `app` with `prefix`
3. Sets `app.max_content` as a `max` between `other_app` and `app`

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
async open_db(state):
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

[Lifespan Protocol](https://asgi.readthedocs.io/en/latest/specs/lifespan.html).

There are two decorators: `@app.startup` and `@app.shutdown`. The decorated
functions receive one argument: `state`.

This is a great place to setup database connections and other dependencies that
your application might need.

A shallow copy of the state is passed to each request.

#### Middleware

µHTTP provides two decorators `@app.before` and `@app.after`.

`@app.before` functions receive only a request argument. They are called
before a response is made, i.e. before the route function (if there is one).
Particularly, `request.params` is still empty at this point. This is a great
place to handle bad requests. The early response pattern:

```python
from uhttp import App, Response

app = App()

@app.before
def auth(request):
    if 'user' not in requet.state:
        raise Response(401)
```

`@app.after` functions receive a `request` and a `response`. They are called
after a response is made. You should modify the response here. **Responses
cannot be raised at this point.**

```python
@app.after
def log(request, response):
    print(request.method, request.path)
    ...
```

#### Route functions

The main route decorator is `@app.route(path, methods=('GET',))`. There's also
specific route decorators for all the standard methods: `@app.get, @app.head,
@app.post, @app.put, @app.delete, @app.connect, @app.options, @app.trace,
@app.patch`.

The `path` parameter is present on all decorators. µHTTP handles paths as
regular expressions. To define path parameters like `/user/<id>` you can use
named groups:

```python
@app.patch('/users/(?P<id>\d+)')
def users(request):
    user_id = request.params['id']
    return {'user': request.state['db']['user_id']}
```

To improve performance, all path regular expressions are compiled at startup.

The response comes from the return value of the route function. If there is no
return, the response defaults to `204 No Content`. The return values can be:
`int` (status), `str` (body), `bytes` (raw body), `dict` (JSON) and
`Response`. 

If the request doesn't match any path, response is set to `404 Not Found`. If
the request doesn't match any of the path methods, response is set to `405
Method Not Allowed`.

µHTTP doesn't support static files. It shouldn't. But if you need them:

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

_No, you don't need to import them._

#### `class Request`

Parameters / Attributes:

- `method`:  `str`
- `path`: `str`
- `params`: `dict`
- `args`: `MultiDict`
- `headers`: `MultiDict`
- `cookies`: `SimpleCookie`
- `body`: `bytes`
- `json`: `dict`
- `form`: `MultiDict`
- `state`: `dict`

**Currently**, µHTTP doesn't support `multipart/form-data` requests. Here's an
implementation with [`multipart`](https://pypi.org/project/multipart/):

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

_Yes, they are wrong._

#### `class Response(Exception)`

Parameters / Attributes:

- `status`: `int`
- `description`: `str` (attribute derived from `status`)
- `headers`: `MultiDict`
- `cookies`: `SimpleCookie`
- `body`: `bytes`

Response inherits from Exception. This is quite handy: In `@app.before`
functions you can raise early responses and `@app.route` may call other
`@app.route` functions.

µHTTP doesn't support templating engines. However, implementing
[Jinja](https://jinja.palletsprojects.com/en/3.1.x/) is very easy:

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

### More

_Read the source code. It will cost you all of 5 minutes._

## Contributing

Feel free to fork, complain, improve, document, fix typos...

## License

Released under the MIT License.

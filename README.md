# µHTTP 

Pythonic web development

## About

µHTTP emerged from the need of a simple, hassle-free web framework. It's great for microservices, single page applications, AND monolithic monsters. 

In µHTTP there is no hidden logic. Everything is what it seems.

### Installation

µHTTP is on [PyPI](https://pypi.org/project/uhttp/).

```bash
pip install uhttp
```

You might also need a web server. µHTTP follows the [ASGI](https://asgi.readthedocs.io/en/latest/) specification. A nice implementation is [Uvicorn](https://www.uvicorn.org/).

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

### Why

- Stupid simple, seriously there are maybe 15 lines of "real" code in it. No external dependencies.
- Extremely modular, entire extensions can just follow the simple App pattern.
- **Very** opinionated, to the point where it has no opinions.
- Fast, because it doesn't really do much.
- Not about types.

### Motivations

_If there is such a thing as "web framework hopping", I've done it in the past few months._

I was writing this very simple application part of a bigger project. All it did was compile information from a whole bunch of APIs.

First, I tried really hard to make [WSGI](https://peps.python.org/pep-0333/), more specifically [Flask](https://flask.palletsprojects.com/en/3.0.x/), to work. Now, if you install [`flask[async]`](https://flask.palletsprojects.com/en/3.0.x/async-await/), it allows you to use co-routines in routes, which is awesome. The best way to make a whole bunch API calls through HTTP is to make them concurrently. But the response times were high (even with concurrency), sometimes ugly Jo's API would take 20s to answer. So that made it really hard for [WSGI](https://asgi.readthedocs.io/en/latest/introduction.html#what-s-wrong-with-wsgi). Well, I suppose, If using WSGI was REALLY important, maybe for backwards compatibility, I could go with something like gevent or eventlet. But the project was new, and I just wanted something simple and clean.

Naturally, as I really liked Flask, I went for [Quart](https://quart.palletsprojects.com/). Well... AFAIK [Phil Jones](https://github.com/pgjones) (author of Quart) is a magician, and the future for Flask (when it finally supports ASGI properly) looks promising. But, for now, things just look extra-hacky. E.g.: to access a 'name' field in a form in Flask you do: `request.form["name"]`; In Quart (one-liner) is `(await request.form)["name"]`. Getters shouldn't be coroutines. Quart is trying really hard to push things forward, but it has too much baggage.

Then I looked at [Sanic](https://sanic.dev/en/). It promised to be unopinionated and flexible. After spending three days modifying the default behavior, I gave up. Really, it is all but unopinionated. It just feels like a "brand" web framework, if there is such a thing. It does all whole bunch of stuff that you don't need and all that you need it doesn't do. Also, weird things were happening with the built-in server.

Now, at that point, I just about had it. Oh, the frustration... So, I decided to see what [ASGI](https://asgi.readthedocs.io/en/latest/) was all about, and why was it so hard to write a proper framework based on it. After reading that tiny spec, my mind was just blown. WTF is it really that simple?! After two hours, the first iteration of µHTTP, thonny, came to life. I used it on our project. And for a while there, I could swear that the air felt lighter. But, it was a company project, and thonny just couldn't handle another shitty feature.

So came [Starlette](https://www.starlette.io/) and [FastAPI](https://fastapi.tiangolo.com/). Wow, I mean, wow! All other frameworks look like toys compared to Starlette. Starlette is unopinionated and flexible. But, it is not simple. So, FastAPI solved that, making it really easy. After rewriting part of the code base to play well with typing notations, things worked really well.

But, I just couldn't forget thonny. I wanted to KISS him so bad. So, in a two-day haze I turned thonny into µHTTP.

I think it solved, cleanly and simply, all of the imaginary problems I had in web development.

## Reference

### Application

_In µHTTP everything is an app._

#### `class App`

Attributes:

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

`app.mount` is µHTTP modularity. What it does:

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

Lifespan functions are based on the [Lifespan Protocol](https://asgi.readthedocs.io/en/latest/specs/lifespan.html).

There are two decorators: `@app.startup` and `@app.shutdown`. Decorated functions receive one argument: `state`.

This is a great place to setup database connections and other dependencies that your application might need.

A shallow copy of the state is passed to each request.

#### Middleware

µHTTP provides two decorators `@app.before` and `@app.after`.

Any value returned from the decorated functions will set the response and break the control flow.

`@app.before` functions receive only a request argument. They are called before a response is made, i.e. before the route function (if there is one). Particularly, `request.params` is still empty at this point. This is a great place to handle bad requests. The early response pattern:

```python
from uhttp import App, HTTPException

app = App()

@app.before
def auth(request):
    if 'user' not in requet.state:
        raise HTTPException(401)
    if request.state['user']['credits'] < 1:
        return 402
```

`@app.after` functions receive a `request` and a `response`. They are called after a response is made. You should modify the response here. `HTTPException` shouldn't be raised here.

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

_No, you don't need to import them._

#### `class Request`

Attributes:

- `method`: `str`
- `path`: `str`
- `params`: `dict`
- `args`: `MultiDict`
- `headers`: `MultiDict`
- `cookies`: `SimpleCookie`
- `body`: `bytes`
- `json`: `dict`
- `form`: `MultiDict`
- `state`: `dict`

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
            raise HTTPException(400)
```

### Responses

_Relax, they already know._

#### `class Response`

Attributes:

- `status`: `int`
- `headers`: `MultiDict`
- `cookies`: `SimpleCookie`
- `body`: `bytes`

#### `response.from_any(any)`

Returns a response based on `any`.

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

### HTTPException

_Raise 'em, don't, what do I care?_

#### `class HTTPException(Exception)`

Attributes:

- `status`: `int`
- `description`: `str`

They should be raised at `@app.before` or `@app.route` functions.

### MultiDict

_I wish you hadn't been born._

#### class MultiDict(dict)

Shares the same attributes as dict. Required because of HTTP 1.1 quirks. You should probably forget its existance.

### `asyncfy(func, /, *args, **kwargs)`

_Simply beautiful._

The function that allows for synchronous code in µHTTP. As long as you use thread-safe code things should be ok. E.g. instead of opening one `sqlite3` connection at startup, consider opening one for every request or just using [`aiosqlite`](https://github.com/omnilib/aiosqlite).

### More

_Read the source code. It will cost you all of 5 minutes._

## Contributing

Feel free to fork, complain, improve, document, fix typos...

## Tests

Well, I don't really see a need for them. But, if you do, feel free to contribute.

## License

Released under the MIT License.

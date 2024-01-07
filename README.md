# µHTTP - Pythonic Web Development

### Why

- Easy: intuitive, clear logic
- Simple: small code base, no external dependencies
- Modular: application mounting, custom route behavior
- Flexible: unopinionated, paradigm-free
- Fast: minimal overhead
- Safe: small attack surface

### Installation

µHTTP is on [PyPI](https://pypi.org/project/uhttp/).

```bash
pip install uhttp
```

Also, an [ASGI](https://asgi.readthedocs.io/en/latest/) server might be needed.

```bash
pip install uvicorn
```

### Hello, world!

```python
from uhttp import Application

app = Application()

@app.get('/')
def hello(request):
    return f'Hello, {request.ip}!'


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('__main__:app')
```

## Documentation

### Application

An [ASGI](https://asgi.readthedocs.io/en/latest/) application. Called once per request by the server.

```python
Application(*, routes=None, startup=None, shutdown=None, before=None, after=None, max_content=1048576)
```

E.g.:

```python
app = Application(
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

#### Application Mounting

Mounts another application at the specified prefix.

```python
app.mount(another, prefix='')
```

E.g.:

```python
utils = Application()

@utils.before
def incoming(request):
    print('Incoming from {request.ip}')

app.mount(utils)
```

#### Application Lifespan (Startup)

Append the decorated function to the list of functions called at the beginning of the [Lifespan](https://asgi.readthedocs.io/en/latest/specs/lifespan.html) protocol.

```python
@app.startup
[async] def func(state)
```

E.g.:

```python
@app.startup
async def open_db(state):
    state['db'] = await aiosqlite.connect('db.sqlite')
```

#### Application Lifespan (Shutdown)

Appends the decorated function to the list of functions called at the end of the Lifespan protocol.

```python
@app.shutdown
[async] def func(state)
```

E.g.:

```python
@app.shutdown
async def close_db(state):
    await state['db'].close()
```

#### Application Middleware (Before)

Appends the decorated function to the list of functions called before a response is made.

```python
@app.before
[async] def func(request)
```

E.g.:

```python
@app.before
def restricted(request):
    user = request.state['session'].get('user')
    if user != 'admin':
        raise Response(401)
```

#### Application Middleware (After)

Appends the decorated function to the list of functions called after a response is made.

```python
@app.after
[async] def func(request, response)
```

E.g.:

```python
@app.after
def logger(request, response):
    print(request, '-->', response)
```

#### Application Routing

Inserts the decorated function to the routing table.

```python
@app.route(path, methods=('GET',))
[async] def func(request)
```

Paths are compiled at startup as regular expression patterns. Named groups define path parameters.

If the request path doesn't match any route pattern, a `404 Not Found` response is returned.

If the request method isn't in the route methods, a `405 Method Not Allowed` response is returned.

Decorators for the standard methods are also available:

```python
@app.get(path)
@app.head(path)
@app.post(path)
@app.put(path)
@app.delete(path)
@app.connect(path)
@app.options(path)
@app.trace(path)
@app.patch(path)
```

E.g.:

```python
@app.route('/', methods=('GET', 'POST'))
def index(request):
    return f'{request.method}ing from {request.ip}'

@app.get(r'/user/(?P<id>\d+)')
def profile(request):
    user = request.state['db'].get_or_404(request.params['id'])
    return '{user.name} has {user.friends} friends and lives in {user.location}'
```

### Request

An HTTP request. Created every time the application is called on the HTTP protocol with a shallow copy of the state.

```python
Request(method, path, *, ip='', params=None, args=None, headers=None, cookies=None, body=b'', json=None, form=None, state=None)
```

### Response

An HTTP Response.

```python
Response(status, *, headers=None, cookies=None, body=b'')
```

E.g.:

```python
@app.startup
def open_db(state):
    state['db'] = {
        1: {
            'name': 'admin',
            'likes': ['terminal', 'old computers']
        },
        2: {
            'name': 'john',
            'likes': ['animals']
        }
    }

def get_or_404(db, id):
    if user := db.get(id):
        return user
    else:
        raise Response(404)

@app.get(r'/user/(?P<id>\d+)')
def profile(request):
    user = get_or_404(request.state['db'], request.params['id'])
    if request.args.get('json'):
        return user
    else:
        return "{user['name']} likes {', '.join(user['likes'])}"
```

## Patterns

### Sessions

Session implementation based on [JavaScript Web Signatures](https://datatracker.ietf.org/doc/html/rfc7515). Sessions are stored in the client's browser as a tamper-proof cookie. Depends on [PyJWT](https://pypi.org/project/PyJWT/).

```python
import os
import time
import jwt
from uhttp import Application, Response

app = Application()
secret = os.getenv('APP_SECRET', 'dev')

@app.before
def get_token(request):
    session = request.cookies.get('session')
    if session and session.value:
        try:
            request.state['session'] = jwt.decode(
                jwt=session.value,
                key=secret,
                algorithms=['HS256']
            )
        except jwt.exceptions.PyJWTError:
            request.state['session'] = {'exp': 0}
            raise Response(400)
    else:
        request.state['session'] = {}

@app.after
def set_token(request, response):
    if session := request.state.get('session'):
        session.setdefault('exp', int(time.time()) + 604800)
        response.cookies['session'] = jwt.encode(
            payload=session,
            key=secret,
            algorithm='HS256'
        )
        response.cookies['session']['expires'] = time.strftime(
            '%a, %d %b %Y %T GMT', time.gmtime(session['exp'])
        )
        response.cookies['session']['samesite'] = 'Lax'
        response.cookies['session']['httponly'] = True
        response.cookies['session']['secure'] = True
```

### Multipart Forms

Support for multipart forms. Depends on [python-multipart](https://pypi.org/project/python-multipart/).

```python
from multipart.multipart import FormParser, parse_options_header
from multipart.exceptions import FormParserError
from uhttp import Application, MultiDict, Response

app = Application()

def parse_form(request):
    form = MultiDict()

    def on_field(field):
        form[field.field_name.decode()] = field.value.decode()
    def on_file(file):
        if file.field_name:
            form[file.field_name.decode()] = file.file_object
    content_type, options = parse_options_header(
        request.headers.get('content-type', '')
    )
    try:
        parser = FormParser(
            content_type.decode(),
            on_field,
            on_file,
            boundary=options.get(b'boundary'),
            config={'MAX_MEMORY_FILE_SIZE': float('inf')}  # app._max_content
        )
        parser.write(request.body)
        parser.finalize()
    except FormParserError:
        raise Response(400)
    return form

@app.before
def handle_multipart(request):
    if 'multipart/form-data' in request.headers.get('content-type'):
        request.form = parse_form(request)
```

### Static Files

Static files for development.

```python
import os
from mimetypes import guess_type
from uhttp import Application, Response

app = Application()

def send_file(path):
    if not os.path.isfile(path):
        raise RuntimeError('Invalid file')
    mime_type = guess_type(path)[0] or 'application/octet-stream'
    with open(path, 'rb') as file:
        content = file.read()
    return Response(
        status=200,
        headers={'content-type':  mime_type},
        body=content
    )

@app.get('/assets/(?P<path>.*)')
def assets(request):
    directory = 'assets'
    path = os.path.realpath(
        os.path.join(directory, request.params['path'])
    )
    if os.path.commonpath([directory, path]) == directory:
        if os.path.isfile(path):
            return send_file(path)
        if os.path.isdir(path):
            index = os.path.join(path, 'index.html')
            if os.path.isfile(index):
                return send_file(index)
    return 404
```

## Contributing

All contributions are welcomed.

## License

Released under the MIT license.

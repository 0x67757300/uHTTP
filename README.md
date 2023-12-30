# µHTTP - Stupid web development

µHTTP emerged from the need of a simple web framework. It's great for micro-services, small applications, AND monolithic monsters.

_In µHTTP there is no hidden logic. Everything is what it seems._

### Why

- Stupid simple, seriously, there are maybe 15 lines of "real" code in it. _No external dependencies._
- Extremely modular, entire extensions can just follow the simple App pattern.
- Very flexible, you can even raise responses.
- Quite fast, because size matters.
- Safe, due to its small attack surface.
- Great learning device.

[The rant.](https://lobste.rs/s/ukh5id/uhttp_pythonic_web_development#c_9jln1d)

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
from uhttp import App

app = App()

@app.get('/')
def hello(request):
    return f'Hello, {request.ip}!'
```

### Example

```python
#!/usr/bin/env python3

from uhttp import App, Response


app = App()


@app.startup
def open_db(state):
    state['clients'] = []
    state['db'] = [
        {
            'title': 'The Art of Riding Bunnies: A Comprehensive Guide.',
            'author': 'grace'
        },
        {
            'title': 'Vanilla Infusions: Culinary Delights and Sweet Sensations.',
            'author': 'joe'
        }
    ]


@app.before
def log_client(request):
    request.state['clients'].append({
        'ip': request.ip,
        'user-agent': request.headers.get('user-agent')
    })


@app.before
def incoming(request):
    print(f'Incoming request from {request.ip}')


@app.get('/')
def all_books(request):
    return {'books': request.state['db']}


@app.get(r'/(?P<author>\w+)')
def from_author(request):
    return {
        'books': [
            book for book in request.state['db']
            if book['author'] == request.params['author']
        ]
    }


def get_user(request):
    user = request.args.get('user')
    if user not in ('grace', 'joe', 'stevens'):
        raise Response(401)
    return user


@app.post('/')
def new(request):
    request.state['db'].append({
        'title': request.form.get('title', ''),
        'author': get_user(request)
    })
    return 201


@app.after
def cors(request, response):
    if request.headers.get('origin'):
        response.headers['access-control-allow-origin'] = '*'


@app.shutdown
def close_db(state):
    del state['db']


@app.shutdown
def print_all_clients(state):
    for client in state['clients']:
        print(client['ip'], client['user-agent'])


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('__main__:app')
```

### Documentation

[API Reference](https://0x67757300.github.io/uHTTP)

### Extensions

_µHTTP doesn't come with bells and whistles._

If you want more, search for [µHTTP extensions](https://github.com/topics/uhttp-extension).

### Contributing

Feel free to contribute in any way you'd like. :D

### License

Released under the MIT license.

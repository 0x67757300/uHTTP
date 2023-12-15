# µHTTP - Stupid web development

µHTTP emerged from the need of a simple web framework. It's great for micro-services, small applications, AND monolithic monsters.

### Why

- Stupid simple, seriously, there are maybe 15 lines of "real" code in it. _No external dependencies._
- Extremely modular, entire extensions can just follow the simple App pattern.
- Very flexible, you can even raise responses.
- Quite fast, because size matters.
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


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('__main__:app')
```

### Documentation

First, read the [tutorial](https://github.com/0x67757300/uHTTP-Tutorial). It'll show you how to write and deploy a link aggregation platform (read: Hacker News clone).

Then, take look at the [API reference](https://0x67757300.github.io/uHTTP/uhttp.html).

Finally, enjoy the source code. ;)

### Extensions

_µHTTP doesn't come with bells and whistles._

If you want more, search for [µHTTP extensions](https://github.com/topics/uhttp).

### Contributing

Feel free to contribute in any way you'd like. :D

### License

Released under the MIT license.

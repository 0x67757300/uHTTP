# µHTTP - Pythonic web development

µHTTP emerged from the need of a **simple** web framework. It's great for micro-services, single page applications, AND monolithic monsters.

_In µHTTP there is no hidden logic. Everything is what it seems._

### Why

- Stupid simple, seriously there are maybe 15 lines of "real" code in it. No external dependencies.
- Extremely modular, entire extensions can just follow the simple App pattern.
- Very flexible, `Response(Exception)`.
- Quite fast, because it doesn't do much.
- Great learning device.

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

### API Reference

Personally, I recommend that you just read the source code.

However, an auto-generated reference can be found [here](https://0x67757300.github.io/uHTTP/docs/uhttp.html).

### Tutorial

Coming soon...

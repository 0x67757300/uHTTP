# µHTTP - Pythonic web development

µHTTP emerged from the need of a **simple** web framework. It's great for micro-services, small applications, AND monolithic monsters.

_In µHTTP there is no hidden logic. Everything is what it seems._

### Why

- Stupid simple, seriously, there are maybe 15 lines of "real" code in it. _No external dependencies._
- Extremely modular, entire extensions can just follow the simple App pattern.
- Very flexible, because of decisions like being able to raise Responses.
- Quite fast, because it doesn't do much.
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
#!/usr/bin/env python3

from uhttp import App


app = App()


@app.get('/')
def hello(request):
    return f'Hello, {request.ip or "World"}!'


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('__main__:app')
```

### API Reference

[The documentation.](https://0x67757300.github.io/uHTTP/uhttp.html)

### Tutorial

_Coming soon..._

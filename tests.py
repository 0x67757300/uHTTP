from uhttp import App, MultiDict, Response


async def request(app, method, path, query_string=b'', headers=None, body=b''):
    response = {}
    state = {}

    http_scope = {
        'type': 'http',
        'method': method,
        'path': path,
        'query_string': query_string,
        'headers': headers or [],
        'state': state
    }

    async def http_receive():
        return {'body': body, 'more_body': False}

    async def http_send(event):
        if event['type'] == 'http.response.start':
            response['status'] = event['status']
            response['headers'] = MultiDict([
                [k.decode(), v.decode()] for k, v in event['headers']
            ])
        elif event['type'] == 'http.response.body':
            response['body'] = event['body']

    lifespan_scope = {'type': 'lifespan', 'state': state}

    async def lifespan_receive():
        if not response:
            return {'type': 'lifespan.startup'}
        elif 'body' in response:
            return {'type': 'lifespan.shutdown'}
        else:
            return {'type': ''}

    async def lifespan_send(event):
        if event['type'] == 'lifespan.startup.complete':
            await app(http_scope, http_receive, http_send)
        elif 'message' in event:
            message = event['message'].encode()
            response['status'] = 500
            response['headers'] = MultiDict({
                'content-length': str(len(message))
            })
            response['body'] = message

    await app(lifespan_scope, lifespan_receive, lifespan_send)

    return response


async def test_lifespan_startup_fail():
    app = App()

    @app.startup
    def fail(state):
        1 / 0

    response = await request(app, 'GET', '/')
    assert response['status'] == 500
    assert response['body'] == b'ZeroDivisionError: division by zero'


async def test_lifespan_shutdown_fail():
    app = App()

    @app.shutdown
    def fail(state):
        1 / 0

    response = await request(app, 'GET', '/')
    assert response['status'] == 500
    assert response['body'] == b'ZeroDivisionError: division by zero'


async def test_lifespan_startup():
    app = App()

    @app.startup
    def startup(state):
        state['msg'] = 'HI!'

    @app.get('/')
    def say_hi(request):
        return request.state.get('msg')

    response = await request(app, 'GET', '/')
    assert response['body'] == b'HI!'


async def test_lifespan_shutdown():
    app = App()
    msgs = ['HI!']

    @app.startup
    def startup(state):
        state['msgs'] = msgs

    @app.shutdown
    def shutdown(state):
        state['msgs'].append('BYE!')

    await request(app, 'GET', '/')
    assert msgs[-1] == 'BYE!'


async def test_204():
    app = App()

    @app.get('/')
    def nop(request):
        pass

    response = await request(app, 'GET', '/')
    assert response['status'] == 204
    assert response['body'] == b''


async def test_404():
    response = await request(App(), 'GET', '/')
    assert response['status'] == 404


async def test_405():
    app = App()

    @app.route('/', methods=('GET', 'POST'))
    def index(request):
        pass

    response = await request(app, 'PUT', '/')
    assert response['status'] == 405
    assert response['headers'].get('allow') == 'GET, POST'


async def test_413():
    app = App()
    response = await request(
        app, 'POST', '/', body=b' '*(app._max_content + 1)
    )
    assert response['status'] == 413


async def test_methods():
    app = App()
    methods = ('GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'OPTIONS')

    @app.route('/', methods=methods)
    def index(request):
        return request.method

    for method in methods:
        response = await request(app, method, '/')
        assert response['body'] == method.encode()


async def test_path_parameters():
    app = App()

    @app.get(r'/hello/(?P<name>\w+)')
    def hello(request):
        return f'Hello, {request.params.get("name")}!'

    response = await request(app, 'GET', '/hello/john')
    assert response['status'] == 200
    assert response['body'] == b'Hello, john!'


async def test_query_args():
    app = App()
    args = {}

    @app.get('/')
    def index(request):
        args.update(request.args)

    await request(
        app, 'GET', '/', query_string=b'tag=music&tag=rock&type=book'
    )
    assert args == {'tag': ['music', 'rock'], 'type': ['book']}


async def test_headers():
    app = App()
    headers = {}

    @app.get('/')
    def hello(request):
        headers.update(request.headers)

    await request(app, 'GET', '/', headers=[[b'from', b'test@example.com']])
    assert headers == {'from': ['test@example.com']}


async def test_cookie():
    app = App()

    @app.get('/')
    def index(request):
        return request.cookies.output(header='Cookie:')

    response = await request(
        app, 'GET', '/', headers=[[b'cookie', b'id=1;name=john']]
    )
    assert response['body'] == b'Cookie: id=1\r\nCookie: name=john'


async def test_set_cookie():
    app = App()

    @app.get('/')
    def index(request):
        return Response(status=204, cookies={'id': 2, 'name': 'jane'})

    response = await request(app, 'GET', '/')
    assert response['headers']._get('set-cookie') == ['id=2', 'name=jane']


async def test_bad_json():
    app = App()

    response = await request(
        app,
        'POST',
        '/',
        headers=[[b'content-type', b'application/json']],
        body=b'{"some": 1'
    )
    assert response['status'] == 400


async def test_good_json():
    app = App()
    json = {}

    @app.post('/')
    def index(request):
        json.update(request.json)

    await request(
        app,
        'POST',
        '/',
        headers=[[b'content-type', b'application/json']],
        body=b'{"some": 1}'
    )
    assert json == {'some': 1}


async def test_json_response():
    app = App()

    @app.get('/')
    def json_hello(request):
        return {'hello': 'world'}

    response = await request(app, 'GET', '/')
    assert response['status'] == 200
    assert response['headers']['content-type'] == 'application/json'
    assert response['body'] == b'{"hello": "world"}'


async def test_form():
    app = App()
    form = {}

    @app.post('/')
    def submit(request):
        form.update(request.form)

    await request(
        app,
        'POST',
        '/',
        headers=[[b'content-type', b'application/x-www-form-urlencoded']],
        body=b'name=john&age=27'
    )

    assert form == {'name': ['john'], 'age': ['27']}


async def test_early_response():
    app = App()

    @app.before
    def early(request):
        return "Hi! I'm early!"

    @app.route('/')
    def index(request):
        return 'Maybe?'

    response = await request(app, 'GET', '/')
    assert response['status'] == 200
    assert response['body'] == b"Hi! I'm early!"


async def test_late_early_response():
    app = App()

    @app.after
    def early(request, response):
        response.status = 200
        response.body = b'Am I early?'

    response = await request(app, 'POST', '/')
    assert response['status'] == 200
    assert response['body'] == b'Am I early?'
    assert response['headers'].get('content-length') == '11'

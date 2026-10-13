"""Import and HTTP boundaries are parsed, including a deliberately forbidden control."""
import ast
import json
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def violations(source, layer):
    tree = ast.parse(source)
    bad = []
    banned = ('fastapi','sqlalchemy','redis','psycopg','pydantic')
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node,ast.Import) else []
        if isinstance(node,ast.ImportFrom):
            module = resolve_name('.'*node.level+(node.module or ''),'app.'+layer) if node.level else node.module or ''
            names = [module, *[module+'.'+alias.name for alias in node.names]]
        for name in names:
            if name.split('.')[0] in banned or name.startswith(('app.adapters','app.api','app.bootstrap','app.models','app.db','app.security','app.schemas')):
                bad.append(name)
            if layer == 'domain' and name.startswith('app.application'): bad.append(name)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in ('__import__','eval','exec'): bad.append(node.func.id)
    return bad

def test_import_boundaries_have_negative_control():
    assert 'sqlalchemy' in violations('from sqlalchemy import select','application')
    assert violations('from .. import bootstrap','application')
    assert violations('from ..adapters.db import models','domain')
    assert violations('import app.adapters.db.models','domain')
    assert violations('from app.application.dto import Principal','domain')
    for layer in ('domain','application'):
        for path in (ROOT/'app'/layer).rglob('*.py'):
            assert not violations(path.read_text(encoding='utf-8'),layer), path

def test_api_has_no_sql_or_concrete_adapters():
    for path in (ROOT/'app'/'api').rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom): assert not (node.module or '').startswith(('sqlalchemy','app.adapters','app.db','app.models')), path
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                assert node.func.attr not in ('scalar','scalars','flush','commit','rollback','add','add_all'), (path,node.lineno)
    tree = ast.parse((ROOT/'app/main.py').read_text(encoding='utf-8'))
    assert len(tree.body) == 2 and isinstance(tree.body[0],ast.ImportFrom)

def test_all_original_api_routes_and_operation_names_remain():
    from app.main import app
    expected = {tuple(item) for item in json.loads((ROOT/'tests/api_contract.json').read_text(encoding='utf-8'))}
    schema = app.openapi()
    actual = {(method.upper(),path) for path,operations in schema['paths'].items() if path.startswith('/api/v1/') for method in operations}
    assert actual == {(method,path) for method,path,name in expected}
    for method,path,name in expected:
        assert schema['paths'][path][method.lower()]['operationId'].startswith(name+'_')
    assert schema['components']['schemas']['ProfileIn']['properties']['role']['enum'] == ['admin','dispatcher','teacher','student']
    assert schema['paths']['/api/v1/lessons']['get']['parameters'][-1]['schema']['maximum'] == 500


def transport_contracts(source):
    """Catch response state, status-based branching and header policy in inner layers."""
    bad=[]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node,ast.Attribute) and node.attr in ('status','status_code','headers'):
            bad.append(node.attr)
        if isinstance(node,(ast.Name,ast.arg)):
            name=node.id if isinstance(node,ast.Name) else node.arg
            if name in ('HTTPStatus','HTTPException','JSONResponse','status_code','headers'):
                bad.append(name)
        if isinstance(node,ast.keyword) and node.arg in ('status_code','headers'):
            bad.append(node.arg)
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            value=node.value.lower()
            if 'retry-after' in value or 'status=' in value:
                bad.append(value)
        if isinstance(node,ast.Call) and node.args:
            name = node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            first=node.args[0]
            if (name.endswith('Error') or name=='__init__') and isinstance(first,ast.Constant) and isinstance(first.value,int) and 100<=first.value<600:
                bad.append('numeric response error')
    return bad

def test_domain_and_application_do_not_own_http_error_contracts():
    controls=["self.status = 401", "if exc.status == 401: pass", "raise ApplicationError(429, 'limited')", "super().__init__(503, 'unavailable')", "return {'Retry-After':'3'}", "logger.info('status=200')"]
    assert all(transport_contracts(control) for control in controls)
    for layer in ('domain','application'):
        for path in (ROOT/'app'/layer).rglob('*.py'):
            assert not transport_contracts(path.read_text(encoding='utf-8')),path

def test_application_use_case_executes_with_framework_imports_blocked():
    # A fresh interpreter proves imports are not merely already cached by other tests.
    import subprocess,sys,textwrap
    code=textwrap.dedent("""
        import importlib.abc,sys
        class NoFrameworks(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.split('.')[0] in ('fastapi','sqlalchemy','redis','psycopg','pydantic'):
                    raise AssertionError('Inner use case imported '+fullname)
        sys.meta_path.insert(0,NoFrameworks())
        from types import SimpleNamespace
        from app.application.auth import Login
        from app.application.common import Services
        from app.application.ports import LimitDecision
        from app.domain.errors import RateLimited
        def forbidden_uow(context): raise AssertionError('Denied write entered UoW')
        limiter=SimpleNamespace(consume=lambda policy,buckets:LimitDecision(False,12))
        services=Services(forbidden_uow,limiter,None,None,None,False)
        try:
            Login(services).execute('example','password','','client')
            raise AssertionError('Expected semantic denial')
        except RateLimited as exc:
            assert exc.retry_after_seconds==12 and exc.policy=='login'
            assert not hasattr(exc,'status') and not hasattr(exc,'headers')
        print('FRAMEWORK_FREE_USE_CASE_OK')
    """)
    result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert 'FRAMEWORK_FREE_USE_CASE_OK' in result.stdout

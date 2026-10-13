"""Transport error contracts belong only to the HTTP adapter."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.errors import install_errors
from app.domain.errors import (ApplicationError, NotFound, Forbidden, Unauthorized,
    Conflict, Validation, BulkWriteRejected, CapacityExceeded, RateLimited, DependencyUnavailable)

@pytest.mark.parametrize('error,status,detail,retry',[
    (NotFound(),404,'Запись не найдена',None),
    (NotFound('Not Found'),404,'Not Found',None),
    (Forbidden(),403,'Forbidden',None),
    (Unauthorized('Неверный логин или пароль'),401,'Неверный логин или пароль',None),
    (Conflict({'message':'Время уже занято','conflicts':[]}),409,{'message':'Время уже занято','conflicts':[]},None),
    (Validation('Дата занятия вне учебного периода'),422,'Дата занятия вне учебного периода',None),
    (BulkWriteRejected(),400,'Массовое изменение записей недоступно',None),
    (CapacityExceeded(),503,'Сейчас открыто много демонстраций. Попробуйте позже.',None),
    (RateLimited('login',12),429,'Слишком много попыток. Повторите через 15 минут.','12'),
    (RateLimited('guest',30),429,'Слишком много новых демонстраций. Попробуйте через 15 минут.','30'),
    (RateLimited('guest_reset',45),429,'Слишком много действий. Подождите минуту.','45'),
    (DependencyUnavailable('redis'),503,'Сервер занят или база временно недоступна. Подождите несколько секунд и проверьте состояние данных.','3'),
    (DependencyUnavailable('postgresql'),503,'Сервер занят или база временно недоступна. Подождите несколько секунд и проверьте состояние данных.','3'),
    (ApplicationError('internal diagnostic'),500,'Внутренняя ошибка сервера',None),
])
def test_semantic_failure_maps_to_exact_http_contract(error,status,detail,retry):
    app=FastAPI()
    install_errors(app)
    @app.get('/failure')
    def failure(): raise error
    response=TestClient(app).get('/failure')
    assert response.status_code==status
    assert response.json()=={'detail':detail}
    assert response.headers.get('retry-after')==retry
    assert not hasattr(error,'status') and not hasattr(error,'headers')

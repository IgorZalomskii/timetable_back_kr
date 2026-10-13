"""Meaningful failures shared by policies and use cases, independent of transport."""

class ApplicationError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(str(message))

class NotFound(ApplicationError):
    def __init__(self, message='Запись не найдена'): super().__init__(message)

class Forbidden(ApplicationError):
    def __init__(self, message='Forbidden'): super().__init__(message)

class Unauthorized(ApplicationError):
    def __init__(self, message='Войдите в приложение'): super().__init__(message)

class Conflict(ApplicationError):
    pass

class Validation(ApplicationError):
    pass

class BulkWriteRejected(ApplicationError):
    def __init__(self): super().__init__('Массовое изменение записей недоступно')

class CapacityExceeded(ApplicationError):
    def __init__(self): super().__init__('Сейчас открыто много демонстраций. Попробуйте позже.')

class RateLimited(ApplicationError):
    def __init__(self, policy, retry_after_seconds):
        self.policy = policy
        self.retry_after_seconds = retry_after_seconds
        super().__init__('Rate limit exceeded')

class DependencyUnavailable(ApplicationError):
    def __init__(self, dependency):
        self.dependency = dependency
        super().__init__('Dependency unavailable: '+dependency)

import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'this is a secr3t'
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    REDIS_PREFIX = 'wilsa'
    SOCKETIO_PATH = ''

    @staticmethod
    def init_app(app):
        pass

class BenchmarkConfig(Config):
    DEBUG = False
    REDIS_URL = os.environ.get("REDIS_URL", "redis://@newplunder:6379/0")

class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True


class ProductionConfig(Config):
    pass

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
    'benchmark': BenchmarkConfig
}

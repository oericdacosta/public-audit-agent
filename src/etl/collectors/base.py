from abc import ABC, abstractmethod

class BaseCollector(ABC):
    def __init__(self, db_manager, client):
        self.db_manager = db_manager
        self.client = client

    @abstractmethod
    def run(self, municipio_id, year):
        pass

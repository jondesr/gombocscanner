from __future__ import annotations
from enum import Enum
from pydantic import BaseSettings

class DataSource(Enum):
    NEO4J = "neo4j"
    PICKLE = "pickle"

class Settings(BaseSettings):
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        use_enum_values = True

    DATASOURCE: DataSource = DataSource.PICKLE
    NEO4J_URL: str
    NEO4j_USER: str
    NEO4j_PASSWORD: str
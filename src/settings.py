from __future__ import annotations
from pydantic import BaseSettings

class Settings(BaseSettings):
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

    NEO4J_URL: str
    NEO4j_USER: str
    NEO4j_PASSWORD: str
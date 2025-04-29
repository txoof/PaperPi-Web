from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Configuration settings for the PaperPi web interface.

    Attributes:
        daemon_url (str): The base URL of the PaperPi daemon API.
    """
    daemon_url: str = 'http://localhost:2822'

def get_settings() -> Settings:
    """
    Dependency-injectable function to retrieve settings for use in FastAPI routes.

    Returns:
        Settings: The current configuration settings instance.
    """
    return Settings()
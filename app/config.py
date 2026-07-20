from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Examinator"
    database_url: str = "sqlite:////opt/exam-simulator/data/exams.db"
    secret_key: str = "change-me-in-production-use-env-var"
    questions_per_session: int = 50
    session_cookie: str = "certsim_user_id"
    admin_email: str = "michel@aguilera.ch"

    class Config:
        env_file = "/opt/exam-simulator/.env"


settings = Settings()

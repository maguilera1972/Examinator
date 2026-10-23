from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Examinator"
    database_url: str = "sqlite:////opt/exam-simulator/data/exams.db"
    secret_key: str = "change-me-in-production-use-env-var"
    questions_per_session: int = 50
    session_cookie: str = "certsim_user_id"
    admin_email: str = "michel@aguilera.ch"
    public_url: str = ""
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    mail_sender: str = "info@aguilera.ch"

    class Config:
        env_file = "/opt/exam-simulator/.env"


settings = Settings()

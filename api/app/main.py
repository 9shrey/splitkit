from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import auth, groups
from app.db import Base, engine
from app.errors import install_error_handlers


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)  # creates missing tables only; never drops data
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Splitkit API", lifespan=lifespan)
    install_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(groups.router)

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    return app


app = create_app()

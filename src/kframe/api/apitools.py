"""FastAPI application with additional configuration options."""

import logging
from enum import Enum

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from fastapi_health import health
from fastapi_pagination import add_pagination
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger("kframe.api")


def config_logging(log_level):
    """Configure logging for the FastAPI application.

    Args:
        log_level (str): Log level.
    """
    green = "\x1b[32;20m"
    dark_grey = "\x1b[90;20m"
    reset = "\x1b[0m"
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["disable_existing_loggers"] = True
    log_config["loggers"]["uvicorn.error"]["level"] = log_level
    log_config["loggers"]["uvicorn.access"]["level"] = log_level
    log_config["formatters"]["default"]["fmt"] = (
        f"{green}%(levelname)s (api.server):{reset} %(message)s {dark_grey}(%(asctime)s.%(msecs)03d){reset}"
    )
    log_config["formatters"]["default"]["datefmt"] = "%Y%m%d-%H:%M:%S"
    log_config["formatters"]["access"]["fmt"] = f"{green}INFO (api.access):{reset} %(message)s"


class API(FastAPI):
    """FastAPI application with additional configuration options."""

    def __init__(self, *args, log_level: str = "ERROR", **kwargs):
        """Create a new FastAPI application.

        Args:
            *args: FastAPI arguments.
            log_level (str, optional): Log level. Defaults to "ERROR".
            **kwargs: FastAPI keyword arguments.
        """
        self.log_level = log_level
        super().__init__(*args, **kwargs)

    def configure_cors(self, cors_config: dict):
        """Configure CORS middleware.

        Args:
            app (Any): FastAPI app.
            cors_config (dict): CORS origins.
        """
        self.add_middleware(
            CORSMiddleware,
            **cors_config,
        )

    def configure_health(self, is_system_online, tag):
        """Configure health check endpoint.

        Args:
            app (Any): FastAPI app.
            is_system_online (Callable[[], bool]): Function to check if the system is online.
            tag (str): Tag for the endpoint.
        """
        self.add_api_route(
            "/health",
            health(is_system_online()),
            include_in_schema=True,
            tags=[tag],
            name="Health",
            description="Health check endpoint.",
            status_code=200,
            responses={
                200: {"status": "online"},
                503: {"description": "System is offline"},
            },
        )
        Instrumentator().instrument(self).expose(self, tags=[tag], should_gzip=True)

    def configure_openapi(
        self,
        version,
        tags_metadata=None,
        title="Service API",
        description="API specification for the service.",
        logo_path: str = "static/logo.png",
        openapi_version="3.1.0",
    ):
        """Configure OpenAPI schema.

        Args:
            app (Any): FastAPI app.
            version (str, optional): API version. Defaults to __api_version__.
            tags_metadata (dict, optional): Tags metadata. Defaults to {}.
            title (str, optional): API title. Defaults to "Service API".
            description (str, optional): API description. Defaults to "API specification for the service.".
            logo_path (str, optional): Logo path. Defaults to "static/logo.png".
            openapi_version (str, optional): OpenAPI version. Defaults to "3.0.3".
        """
        if tags_metadata is None:
            tags_metadata = {}

        def inner():
            """Customize FastAPI's OpenAPI schema.

            Returns:
                Any: OpenAPI schema.
            """
            self.mount("/static", StaticFiles(directory="static"), name="static")

            if self.openapi_schema:
                return self.openapi_schema
            openapi_schema = get_openapi(
                title=title,
                version=version,
                description=description,
                routes=self.routes,
                openapi_version=openapi_version,
                tags=tags_metadata,
            )
            openapi_schema["info"]["x-logo"] = {"url": logo_path}
            self.openapi_schema = openapi_schema
            return self.openapi_schema

        self.openapi = inner  # type: ignore

    def add_pagination(self):
        """Add pagination to the FastAPI app."""
        add_pagination(self)

    def configure_sentry(self, sentry_dsn: str | None, path: str | None = None, tags: list[str | Enum] | None = None):
        """Add Sentry to the FastAPI app.

        Args:
            app (Any): FastAPI app.
            sentry_dsn (str): Sentry DSN.
            path (str, optional): Path to prepend to the Sentry debug endpoint. Defaults to "".
            tags (List[str], optional): Tags for the Sentry debug endpoint. Defaults to ["Sentry"].
        """
        import sentry_sdk

        if tags is None:
            tags = ["Health & Metrics"]

        if path is None:
            path = ""

        if sentry_dsn is not None and sentry_dsn != "":
            sentry_sdk.init(
                dsn=sentry_dsn,
                # Set traces_sample_rate to 1.0 to capture 100%
                # of transactions for performance monitoring.
                traces_sample_rate=1.0,
                # Set profiles_sample_rate to 1.0 to profile 100%
                # of sampled transactions.
                # We recommend adjusting this value in production.
                profiles_sample_rate=1.0,
            )

        @self.get(f"{path}/sentry-debug", tags=tags, name="Sentry Debug")
        def trigger_error():
            """Trigger an error to test Sentry."""
            return 1 / 0

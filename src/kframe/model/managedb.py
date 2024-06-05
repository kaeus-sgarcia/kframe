"""Database management utilities module."""

import logging
from collections.abc import AsyncGenerator, Generator
from functools import cache
from pathlib import Path
from typing import TypedDict

from alembic import command
from alembic import config as alembic_config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from rich.console import Console
from rich.prompt import Prompt
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("am.utils.managedb")

console = Console()


class EngineConfig(TypedDict, total=False):
    """Engine configuration dictionary.

    Args:
        sql_echo (bool): Echo SQL statements.
        pool_size (int): Pool size.
        max_overflow (int): Maximum overflow.
        pool_pre_ping (bool): Enable pool pre-ping.
    """

    sql_echo: bool
    pool_size: int
    max_overflow: int
    pool_pre_ping: bool


class SessionConfig(TypedDict, total=False):
    """Session configuration dictionary.

    Args:
        expire_on_commit (bool): Expire objects on session commit.
    """

    expire_on_commit: bool


class ModelManager:
    """Database manager class."""

    def __init__(
        self,
        host: str,
        port: int,
        name: str,
        user: str,
        password: str,
        driver: str,
        store_name: str = "Database",
        script_location: str = "alembic",
        version_table: str = "db_version",
        engine_config: EngineConfig | None = None,
        session_config: SessionConfig | None = None,
    ):
        """Create a new ModelManager instance.

        Args:
            host (str): Database host.
            port (int): Database port.
            name (str): Database name.
            user (str): Database user.
            password (str): Database password.
            driver (str): Database driver.
            store_name (str, optional): Name of the store. Defaults to "Database".
            script_location (str, optional): Location of the Alembic scripts. Defaults to "alembic".
            version_table (str, optional): Version table name. Defaults to "db_version".
            engine_config (EngineConfig, optional): Engine configuration. Defaults to None.
            session_config (SessionConfig, optional): Session configuration. Defaults to None.
        """
        self._db_url = URL.create(
            drivername=driver,
            username=user,
            password=password,
            host=host,
            port=port,
            database=name,
        )
        self.script_location = script_location
        self.version_table = version_table
        self.store_name = store_name
        if engine_config is None:
            engine_config = {}
        if session_config is None:
            session_config = {}
        self.sql_echo = engine_config.get("sql_echo", False)
        self.pool_size = engine_config.get("pool_size", 1)
        self.max_overflow = engine_config.get("max_overflow", 0)
        self.pool_pre_ping = engine_config.get("pool_pre_ping", True)
        self.expire_on_commit = session_config.get("expire_on_commit", False)

    @property
    def db_url(self) -> URL:
        """Get the database URL.

        Returns:
            URL: Database URL.
        """
        return self._db_url

    @cache
    def engine(self) -> Engine:
        """Get a database engine object.

        Returns:
            Engine: Engine object.
        """
        return create_engine(
            self.db_url,
            echo=self.sql_echo,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_pre_ping=self.pool_pre_ping,
        )

    @cache
    def session_maker(self, **kwargs) -> sessionmaker:
        """Get a database session maker object.

        Args:
            **kwargs: Additional keyword arguments to pass to the sessionmaker.

        Returns:
            sessionmaker: Session maker object.
        """
        return sessionmaker(self.engine(), **kwargs)

    @cache
    def async_engine(self, **kwargs) -> AsyncEngine:
        """Get an async database engine object.

        Args:
            **kwargs: Additional keyword arguments to pass to the async engine.

        Returns:
            AsyncEngine: Async engine object.
        """
        return create_async_engine(self.db_url, echo=self.sql_echo, **kwargs)

    @cache
    def async_session_maker(self, **kwargs) -> async_sessionmaker:
        """Get an async session maker object.

        Args:
            **kwargs: Additional keyword arguments to pass to the async sessionmaker.

        Returns:
            async_sessionmaker: Async session maker object.
        """
        return async_sessionmaker(self.async_engine(), **kwargs)

    @property
    def session(self) -> Generator[Session, None, None]:
        """Get a database sqlalchemy session object.

        Returns:
            Generator[Session, None, None]: Session object.
        """
        return self.session_maker()()

    @property
    async def async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database sqlalchemy async session object.

        Returns:
            AsyncGenerator[AsyncSession, None]: Async session object.
        """
        return self.async_session_maker()()

    @property
    def alembic_config(self):
        """Get the Alembic configuration object.

        Returns:
            alembic_config.Config: Alembic configuration object.
        """
        db_url = self.db_url.render_as_string(hide_password=False).replace("%", "%%")

        if self.script_location is None or Path(self.script_location).exists() is False:
            raise ValueError("db_script_location is not set")

        alembic_cfg = alembic_config.Config()
        alembic_cfg.set_main_option("version_table", self.version_table)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        alembic_cfg.set_main_option("script_location", self.script_location)
        alembic_cfg.set_section_option("logger_alembic", "level", "DEBUG")
        return alembic_cfg

    @property
    def current_revision(self) -> str | None:
        """Get the current database revision.

        Args:
        ----
            config (Config): Configuration object.

        Returns:
        -------
            str: Current database revision.
        """
        engine = create_engine(self.db_url)
        conn = engine.connect()
        context = MigrationContext.configure(conn, opts={"version_table": self.version_table})
        current_rev: str | None = context.get_current_revision()
        return current_rev

    @property
    def heads(self) -> list[str]:
        """Get the possible head migrations for the database.

        Args:
        ----
            config (Config): Configuration object.

        Returns:
        -------
            list: List of possible head migrations)
        """
        script_directory = ScriptDirectory.from_config(self.alembic_config)

        heads = []
        for h in script_directory.get_heads():
            branches = script_directory.get_revision(h).branch_labels
            heads.extend(list(branches))

        return [f"{h}@head" for h in heads]

    @property
    def pending_migrations(self) -> list[tuple[str | None, str, bool]]:
        """Get the pending migrations for the database.

        Args:
        ----
            config (Config): Configuration object.

        Returns:
        -------
            list: List of pending migrations, each item is a tuple of (from_rev: str, to_rev: str, is_current: bool)
        """
        current_version = self.current_revision

        script_directory = ScriptDirectory.from_config(self.alembic_config)

        heads = script_directory.get_heads()

        if current_version in heads:
            return []

        pending_migrations = []
        for sc in script_directory.walk_revisions(base=self.current_revision or "base", head="heads"):
            down_revision: str | None = str(sc.down_revision) if sc.down_revision is not None else None
            if sc.down_revision == current_version:
                pending_migrations.append((down_revision, sc.revision, down_revision == current_version))
                break
            pending_migrations.append((down_revision, sc.revision, down_revision == current_version))

        return pending_migrations[::-1]

    def initialize_db(self) -> None:
        """Initialize the database.

        Args:
        ----
            config (Config): Configuration object.
        """
        if len(self.heads) > 1:
            revision = Prompt.ask(
                "Select revision to initialize the database",
                choices=self.heads,
            )
        else:
            revision = self.heads[0]

        console.print(f"Initializing database to revision [red]{revision}[/red]")

        self.db_upgrade(revision=revision)
        console.print("")

    def db_status(self) -> None:
        """Print the status of the database schema to console.

        Args:
        ----
            config (Config): Configuration object.
            store_name (str): Name of the store.
        """
        current_version = self.current_revision
        pending = self.pending_migrations

        console.print()
        console.rule(f"[bold]{self.store_name} Database Status[/bold]")

        if current_version is None:
            console.print("Database is not initialized")
            migrate = Prompt.ask(
                "Do you want to initialize the database?",
                choices=["y", "n"],
                default="n",
            )
            if migrate == "y":
                self.initialize_db()

        if len(pending) == 0:
            console.print(f"Database is up to date (revision={current_version})\n")
            return None

        console.print(f"Pending {len(pending)} revisions (*=current):")
        for i, migration in enumerate(pending[::-1]):
            from_rev = ((migration[0] or "empty base") + ("*" if migration[2] else "")).ljust(13)
            to_rev = (migration[1] + " (head)" if i == 0 else "").ljust(13)
            console.print(f"\t[red]{from_rev}[/red] --> [red]{to_rev}[/red]")
        console.print()
        migrate = Prompt.ask(
            "Do you want to upgrade the database? [bold][magenta]y/n/(rev)[/magenta][/bold]",
            choices=["y", "n", *[p[1] for p in pending]],
            default="n",
            show_choices=False,
        )
        if migrate != "n":
            revision = "head" if migrate == "y" else migrate
            console.print(f"Upgrading database to revision [red]{revision}[/red]")
            self.db_upgrade(revision=revision)
            console.print("")
            return None

        console.print("")
        return None

    def db_upgrade(self, revision: str = "head") -> None:
        """Upgrade the database to a new revision.

        Args:
        ----
            config (Config): Configuration object.
            revision (str, optional): Revision to upgrade to, fefaults to the latest version.
        """
        alembic_cfg = self.alembic_config

        if revision == "head" and len(self.heads) > 1:
            console.print("Multiple heads found")
            revision = Prompt.ask(
                "Select revision to upgrade the database",
                choices=self.heads,
            )
        else:
            revision = self.heads[0] if revision not in self.heads else revision

        with create_engine(self.db_url).begin() as connection:
            alembic_cfg.attributes["connection"] = connection
            command.upgrade(alembic_cfg, revision)
        console.print(f"Database upgraded to revision [red]{self.current_revision}[/red]")

    def db_downgrade(self, revision: str = "-1") -> None:
        """Downgrade the database to a previous revision.

        Args:
        ----
            config (Config): Configuration object.
            revision (str, optional): Revision to downgrade to, defaults to the previous version.
        """
        alembic_cfg = self.alembic_config
        with create_engine(self.db_url).begin() as connection:
            alembic_cfg.attributes["connection"] = connection
            command.downgrade(alembic_cfg, revision)
        console.print(f"Database downgraded to revision [red]{self.current_revision}[/red]")

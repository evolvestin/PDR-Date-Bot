import os
import re
import logging
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder
from functions.base_path import base_path
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

load_dotenv()  # Load environment variables from the .env file
Base = declarative_base()  # Initialize the base class for ORM models
database_url = os.getenv('DATABASE_URL')  # Retrieve the database URL from environment variables

if os.getenv('LOCAL'):
    logging.warning(' SSH Tunneling Postgres connection (testing environment)')
    tunnel = SSHTunnelForwarder(
        (os.getenv('SSH_HOST'), 22),
        remote_bind_address=('127.0.0.1', 5432),
        ssh_username=os.getenv('SSH_USER'),
        ssh_password=os.getenv('SSH_PASS'),
    )
    tunnel.start()  # Start the SSH tunnel
    database_url = re.sub('localhost', f'localhost:{tunnel.local_bind_port}', database_url)

postgres_engine = create_async_engine(database_url, echo=False)  # Create an engine for Postgres database connection
init_postgres_session = async_sessionmaker(  # Create an asynchronous session for Postgres
    bind=postgres_engine,
    expire_on_commit=False,
)

sqlite_engine = create_async_engine(f"sqlite+aiosqlite:///{base_path.joinpath('database', 'local.db')}", echo=False)
init_sqlite_session = async_sessionmaker(  # Create an asynchronous session for SQLite database
    bind=sqlite_engine,
    expire_on_commit=False,
)


async def init_database(postgres_tables: list[str], sqlite_tables: list[str]) -> None:
    """
    Initialize the database by creating specified tables if they do not already exist.

    This function creates tables in both Postgres and SQLite databases based on the provided table names.

    :param postgres_tables: List of table names to be created in the Postgres database.
    :type postgres_tables: list[str]

    :param sqlite_tables: List of table names to be created in the SQLite database.
    :type sqlite_tables: list[str]
    """
    if postgres_tables:
        # Prepare the list of Postgres tables to create
        tables_to_create = [Base.metadata.tables[table_name] for table_name in postgres_tables]
        async with postgres_engine.begin() as connection:
            # Create the tables in Postgres
            await connection.run_sync(Base.metadata.create_all, tables=tables_to_create)
    if sqlite_tables:
        # Prepare the list of SQLite tables to create
        tables_to_create = [Base.metadata.tables[table_name] for table_name in sqlite_tables]
        async with sqlite_engine.begin() as connection:
            # Create the tables in SQLite
            await connection.run_sync(Base.metadata.create_all, tables=tables_to_create)

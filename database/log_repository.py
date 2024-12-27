from datetime import datetime
from database.models import Log
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.session import init_sqlite_session


class LogRepository:
    """
    A repository class for managing logs in the database. It provides methods to interact with logs,
    including fetching, inserting, updating, and deleting records.
    """
    async def __aenter__(self) -> 'LogRepository':
        """Creates a session and connects to the database, returns a repository instance"""
        self.connection: AsyncSession = init_sqlite_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes the session when exiting the context, releasing database connection resources"""
        if self.connection:
            await self.connection.close()

    async def get_posted_logs(self) -> list[Log]:
        """
        Fetches all logs that have a non-null post_id, ordered by log ID.

        :return: A list of Log objects that have a non-null post_id.
        :rtype: list[Log]
        """
        result = await self.connection.execute(
            select(Log)
            .where(Log.post_id.isnot(None))
            .order_by(Log.id)
        )
        return list(result.scalars().all())

    async def get_logs_to_post(self) -> list[Log]:
        """
        Fetches all logs that have a null post_id, ordered by log ID.

        :return: A list of Log objects that have a null post_id.
        :rtype: list[Log]
        """
        result = await self.connection.execute(
            select(Log)
            .where(Log.post_id.is_(None))
            .order_by(Log.id)
        )
        return list(result.scalars().all())

    async def insert_log(self, text: str) -> None:
        """
        Inserts a new log record with the provided text into the database.

        :param text: The text of the log to be inserted.
        :type text: str
        """
        self.connection.add(Log(text=text))
        await self.connection.commit()

    async def update_posted_logs(self, record_ids: list[int], post_id: int, post_date: datetime) -> None:
        """
        Updates the post_id and post_date for logs with the specified IDs.

        :param record_ids: A list of log IDs to be updated.
        :type record_ids: list[int]
        :param post_id: The post ID to associate with the logs.
        :type post_id: int
        :param post_date: The post date to associate with the logs.
        :type post_date: datetime
        """
        await self.connection.execute(
            update(Log)
            .where(Log.id.in_(record_ids))
            .values(post_id=post_id, post_date=post_date)
        )
        await self.connection.commit()

    async def remove_posted_logs(self, record_ids: list[int]) -> None:
        """
        Deletes logs with the specified IDs that have a non-null post_id.

        :param record_ids: A list of log IDs to be deleted.
        :type record_ids: list[int]
        """
        await self.connection.execute(
            delete(Log)
            .where(Log.id.in_(record_ids), Log.post_id.isnot(None))
        )
        await self.connection.commit()

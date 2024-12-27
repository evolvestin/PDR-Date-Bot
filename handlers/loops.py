import os
import asyncio
import logging
from handlers import errors
from datetime import datetime, timezone
from services import google_client, Logger, Texts, Users


error_handler = errors.TelegramError()
logger_service = Logger.TelegramLogger()
google_session = google_client.GoogleSheetsSession()

logging.basicConfig(level=logging.INFO)


class TaskHandlers:
    @staticmethod
    async def run_task(function: callable, repeating: bool = True, **kwargs):
        """
        Executes a given asynchronous task, optionally repeating it indefinitely.
        If the task fails due to an exception, it retries after a short delay.

        :param function: The asynchronous function to execute.
        :type function: callable
        :param repeating: Whether to repeat the task indefinitely, defaults to True.
        :type repeating: bool
        :param kwargs: Additional keyword arguments to pass to the function.
        """
        logging.warning(f' Running {function.__name__} (repeating={repeating})')
        while True:
            try:
                await function(**kwargs)
            except IndexError and Exception:
                await errors.TelegramError().handle_error()
                await asyncio.sleep(15)
            if not repeating:
                break

    @staticmethod
    async def logger_queue_handler() -> None:
        """Periodically sends logs to the Telegram channel"""
        await logger_service.send_logs_to_telegram()

    @staticmethod
    async def scheduled_actions() -> None:
        """
        Performs scheduled actions, such as user backups and lot cleanup.
        This task runs periodically and performs actions based on the current
        time. It checks if it's time to back up user data or clean up table of distributed lots.
        """
        now = datetime.now(timezone.utc)
        if now.strftime('%M') in ['05', '15', '25', '55'] or os.getenv('LOCAL'):
            await Users.UsersUpdater().back_up_users()
        await asyncio.sleep(60)

    @staticmethod
    async def init_constants(start_time: datetime = None) -> None:
        """
        Initializes constants and updates configurations during the bot's start sequence.

        - Checks the existence of user and configuration data in the database.
        - If missing, retrieves them from Google Sheets.
        - Updates texts, item constants, and page constants.
        - Validates user subscriptions and restores subscriptions from backup if needed.
        - Sends a startup message upon successful initialization.

        :param start_time: The time the initialization started, used for logging purposes.
        :type start_time: datetime, optional
        """
        spreadsheet = None
        users_updater = Users.UsersUpdater()
        texts_updater = Texts.TextsUpdater()
        texts_exist = await texts_updater.check_texts_exist_in_database()
        users_exist = await users_updater.check_users_exist_in_database()

        if not users_exist or not texts_exist:
            spreadsheet = await google_session.get_spreadsheet(os.getenv('GOOGLE_SHEET_ID'))

        # Restore texts from backup if needed
        if not texts_exist:
            await texts_updater.update_texts_in_local_database(spreadsheet)

        # Restore users from backup if needed
        if not users_exist:
            await users_updater.update_users_in_database(spreadsheet)

        # Send a startup message if the bot is ready
        if os.getenv('LOCAL') is None:
            await logger_service.send_start_message(start_time)
        if start_time:
            now = datetime.now(start_time.tzinfo)
            logging.warning(f" {now.replace(tzinfo=None).isoformat(' ', 'seconds')} run for {now - start_time}")

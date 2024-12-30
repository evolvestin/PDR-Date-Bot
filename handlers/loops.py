import os
import asyncio
import logging
from handlers import errors
from datetime import datetime, timezone
from functions.html import code, blockquote
from database.texts_repository import TextsRepository
from database.user_repository import UserPregnancyRepository
from services import google_client, Keyboards, Logger, Telegram, Texts, Users

sender = Telegram.MessageSender()
user_service = Users.UserService()
texts_service = Texts.TextsService()
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
    async def pdr_date_notify() -> None:
        async with UserPregnancyRepository() as db:
            users = await db.get_users_with_today_pdr(now=datetime.now(timezone.utc))

        for user, pregnancy in users:
            async with TextsRepository() as db_texts:
                texts = await db_texts.get_texts_by_language(user.language)
            text = texts['pdr_notify'].format(user.id, user.full_name)
            await sender.message(chat_id=pregnancy.chat_id, text=text)

            log_text = (
                f"{user.full_name}{f' [@{user.username}]' if user.username else ''} {code(user.id)}:\n"
                f"Оповещение о дате ПДР\n"
                f"Чат: {code(pregnancy.chat_id)}"

            )
            await logger_service.insert_log_to_queue(blockquote(log_text), bot_header=True)
            await asyncio.sleep(1)

    @staticmethod
    async def new_period_notify() -> None:
        async with UserPregnancyRepository() as db:
            pregnancies = await db.get_user_period_pregnancy()

        now = user_service.get_now()
        for user, pregnancy in pregnancies:
            is_notify_allowed = False
            async with TextsRepository() as db_texts:
                texts = await db_texts.get_texts_by_language(user.language)
            user_text_service = Users.UserTextGenerator(user, texts, keys=Keyboards.Keys(user, texts))
            difference, weeks, days = user_text_service.get_weeks_and_days_from_date(now, date=pregnancy.period_date)

            if not pregnancy.pdr_date:
                if weeks <= 40:
                    is_notify_allowed = True
            elif now < pregnancy.pdr_date:
                is_notify_allowed = True

            if days == 0 and is_notify_allowed:
                period_text = texts_service.period_week_and_day(
                    texts=texts,
                    difference_seconds=int(difference.total_seconds()),
                )
                text = texts['period_notify'].format(user.id, user.full_name, period_text)
                await sender.message(chat_id=pregnancy.chat_id, text=text)

                log_text = (
                    f"{user.full_name}{f' [@{user.username}]' if user.username else ''} {code(user.id)}:\n"
                    f"Оповещение о новом периоде: {period_text}\n"
                    f"Чат: {code(pregnancy.chat_id)}"
                )
                await logger_service.insert_log_to_queue(blockquote(log_text), bot_header=True)
                await asyncio.sleep(1)

    async def scheduled_actions(self) -> None:
        """
        Performs scheduled actions, such as user backups and lot cleanup.
        This task runs periodically and performs actions based on the current
        time. It checks if it's time to back up user data or clean up table of distributed lots.
        """
        now = datetime.now(timezone.utc)
        if now.strftime('%M') in ['05', '15', '25', '55'] or os.getenv('LOCAL'):
            await Users.UsersUpdater().back_up_users()
        if now.strftime('%H:%M') == '08:00':
            await self.pdr_date_notify()
        if now.strftime('%H:%M') == '09:00':
            await self.new_period_notify()
        delay = 60 - (datetime.now(timezone.utc) - now).total_seconds()
        await asyncio.sleep(delay if delay > 0 else 0)

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

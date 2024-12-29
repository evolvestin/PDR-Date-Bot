import os
import re
import json
import asyncio
import logging
from typing import Union
from aiogram import types
from datetime import datetime, timezone, timedelta
from gspread_asyncio import AsyncioGspreadSpreadsheet

from functions.html import html_secure
from services.bot_instance import BotInstance
from services import google_client, Keyboards, Telegram, Texts

from database.models import User, UserDate
from database.texts_repository import TextsRepository
from database.user_repository import UserRepository, UserDateRepository


sender = Telegram.MessageSender()
texts_service = Texts.TextsService()
google_session = google_client.GoogleSheetsSession()


class UserService:
    """
    Service for managing user-related operations, including database interactions,
    user dates, and bot-specific functionality such as setting commands
    and handling user reactions.

    This class implements the Singleton pattern to ensure only one instance exists.
    """
    _instance = None  # Attribute to store the single class instance

    def __new__(cls, *args, **kwargs):
        """
        Ensures that only one instance of the class is created.

        :return: The single instance of the class.
        :rtype: UserService
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """Initializes the UserService instance. Sets up bot username and admins variable."""
        if not hasattr(self, 'initialized'):  # Ensure initialization runs only once
            self.initialized = True
            self.bot_username: str = 'bot_username'

    async def update_variable_bot_username(self):
        """Updates the bot's username if it has not been set"""
        if self.bot_username == 'bot_username':
            bot_me = await BotInstance().main_bot.get_me()
            self.bot_username = bot_me.username

    async def get_reaction(self, message: types.ChatMemberUpdated) -> tuple[int, bool]:
        """
        Determines the bot's reaction to a chat member update event.

        :param message: Event object containing details of the chat member update.
        :type message: types.ChatMemberUpdated

        :return: Tuple with reaction status (1 or 0) and whether a chat greeting is needed.
        :rtype: tuple[int, bool]
        """
        await self.update_variable_bot_username()

        new_reaction = None
        chat_greeting = False
        new_member = message.new_chat_member.user
        if new_member.id != message.from_user.id and new_member.username == self.bot_username:
            if message.old_chat_member.status in ['left', 'kicked']:
                new_reaction = 1
                chat_greeting = message.chat.id < 0  # True if the chat is a group or channel
            elif (message.chat.id > 0
                  or message.chat.type == 'channel'
                  or message.new_chat_member.status in ['left', 'kicked']):
                new_reaction = 0
            elif message.new_chat_member.status == 'restricted' and not message.new_chat_member.can_send_messages:
                new_reaction = 0
        return new_reaction, chat_greeting

    @staticmethod
    def message_user_transform_to_model_user(user: types.User) -> User:
        """
        Transforms a Telegram message user object into a User model.

        :param user: Telegram message user.
        :type user: types.User

        :return: User model with details extracted from the user.
        :rtype: User
        """
        return User(
            id=user.id,
            full_name=user.full_name,
            username=user.username,
            language=user.language_code,
        )

    def message_transform_to_model_user(
            self,
            message: Union[types.Message, types.CallbackQuery, types.ChatMemberUpdated]
    ) -> User:
        """
        Transforms a message object into a User model.

        :param message: Telegram message user, reply user.
        :type message: Union[types.Message, types.CallbackQuery, types.ChatMemberUpdated]

        :return: User model with details extracted from the message.
        :rtype: User
        """
        user = self.message_user_transform_to_model_user(message.from_user)
        return user

    async def get_user(
            self, message: Union[types.Message, types.CallbackQuery, types.ChatMemberUpdated]
    ) -> tuple[User, dict[str, str], list[str]]:
        """
        Retrieves or creates a user in the database and updates their personal data if changed.

        :param message: Telegram message, callback query, or chat member update.
        :type message: Union[types.Message, types.CallbackQuery, types.ChatMemberUpdated]

        :return: Tuple containing the User model, localized text dictionary, and log messages.
        :rtype: tuple[User, dict[str, str], list[str]]
        """
        log_texts = []
        new_user = self.message_transform_to_model_user(message)

        async with UserRepository() as db_users:
            user = await db_users.get_user_by_telegram_id(telegram_id=new_user.id)

            async with TextsRepository() as db_texts:
                if not user:
                    log_texts.append('#first_start')
                    language_codes = await db_texts.get_all_language_codes()
                    new_user.language = 'ru' if new_user.language not in language_codes else new_user.language
                    user = await db_users.create_user(new_user, reaction=True)

                if user.full_name != new_user.full_name or user.username != new_user.username:
                    await db_users.update_user_personal_data(
                        user=user,
                        username=new_user.username,
                        full_name=new_user.full_name,
                    )

                texts = await db_texts.get_texts_by_language(user.language)
        return user, texts, log_texts

    @staticmethod
    async def set_commands(chat_id: int, texts: dict[str, str]) -> None:
        """
        Sets the command menu for a user.

        :param chat_id: Telegram chat ID.
        :type chat_id: int
        :param texts: Dictionary of localized texts.
        :type texts: dict[str, str]
        """
        bot_commands = []
        bot = BotInstance().main_bot
        commands: list[dict[str, str]] = json.loads(texts['BOT_COMMANDS'])
        if str(chat_id) in os.getenv('ADMINS'):
            bot_commands = [
                types.BotCommand(command='update_texts', description='Обновить текста из Google Sheets'),
            ]

        for command in commands:
            bot_commands.append(types.BotCommand(**command))

        target_commands = await bot.get_my_commands(types.BotCommandScopeChat(chat_id=chat_id))
        if target_commands != bot_commands:
            await bot.set_my_commands(bot_commands, types.BotCommandScopeChat(chat_id=chat_id))

    @staticmethod
    async def disable_chat_user(user: User) -> None:
        """
        Marks a user as disabled in the database after a chat migration.

        :param user: User model to be disabled.
        :type user: User
        """
        async with UserRepository() as db:
            await db.update_user_username_and_reaction(user, username='DISABLED_GROUP', reaction=False)

    @staticmethod
    async def update_user_reaction(user: User, reaction: int) -> None:
        """
        Updates the user's reaction status in the database.

        :param user: User model to update.
        :type user: User
        :param reaction: Reaction status (1 for active, 0 for inactive).
        :type reaction: int
        """
        async with UserRepository() as db:
            if reaction:
                reaction = True
            else:
                reaction = False
            await db.update_user_reaction(user, reaction)

    @staticmethod
    def get_now():
        return datetime.now(timezone(timedelta(hours=int(os.getenv('TIMEZONE'))))).replace(tzinfo=None)

    async def get_user_date(self, telegram_user: types.User, chat_id: int) -> tuple[User, UserDate, list[str]]:
        log_texts = []
        async with UserRepository() as db_users:
            user = await db_users.get_user_by_telegram_id(telegram_id=telegram_user.id)
            if not user:
                log_texts.append('#first_start')
                async with TextsRepository() as db_texts:
                    language_codes = await db_texts.get_all_language_codes()
                new_user = self.message_user_transform_to_model_user(user=telegram_user)
                new_user.language = 'ru' if new_user.language not in language_codes else new_user.language
                user = await db_users.create_user(new_user, reaction=False)

        async with UserDateRepository() as db_dates:
            date = await db_dates.get_or_create_user_date(user_id=user.id, chat_id=chat_id)
        return user, date, log_texts

    @staticmethod
    async def update_user_period_date(user_id: int, chat_id: int, date: datetime) -> None:
        async with UserDateRepository() as db:
            user_date = await db.get_or_create_user_date(user_id, chat_id)
            await db.update_user_period_date(date=user_date, period_date=date)

    @staticmethod
    async def update_user_pdr_date(user_id: int, chat_id: int, date: datetime) -> None:
        async with UserDateRepository() as db:
            user_date = await db.get_or_create_user_date(user_id, chat_id)
            await db.update_user_pdr_date(date=user_date, pdr_date=date)

    @staticmethod
    async def delete_chat_message(message: types.Message) -> bool:
        deleted = False
        if message.chat.id < 0 and message.reply_to_message:
            deleted = True
            try:
                await BotInstance().main_bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except IndexError and Exception:
                pass
        return deleted


class UserTextGenerator:
    """
    A class for generating text and keyboard interfaces for users in a bot.

    :param user: The user object representing the current bot user.
    :type user: User
    :param texts: A dictionary containing various text templates for the bot.
    :type texts: dict[str, str]
    :param keys: An object for generating keyboards for the bot interface.
    :type keys: Keyboards.Keys
    :param message_text: The text of the current message from the user, defaults to None.
    :type message_text: str, optional
    """
    def __init__(self, user: User, texts: dict[str, str], keys: Keyboards.Keys, message_text: str = None):
        self.user: User = user
        self.keys: Keyboards.Keys = keys
        self.texts: dict[str, str] = texts
        self.message_text: str = message_text or ''
        self.user_service: UserService = UserService()

    @staticmethod
    def get_weeks_and_days_from_date(now: datetime, date: datetime) -> tuple[timedelta, int, int]:
        difference = (now - date)
        weeks = int(difference.days // 7)
        days = difference.days - weeks * 7
        return difference, weeks, days

    def get_example_period_instruction(self, now: datetime) -> tuple[str, int, int]:
        example = datetime.fromisoformat(now.strftime('2024-06-13 %H:%M:%S'))
        example_difference, example_weeks, example_days = self.get_weeks_and_days_from_date(now, date=example)
        example_period_text = texts_service.period_week_and_day(
            texts=self.texts,
            difference_seconds=int(example_difference.total_seconds()),
        )
        text = self.texts['period_instruction'].format(example_weeks, example_days, example_period_text)
        return text, example_weeks, example_days

    async def get_pdr_or_period_info(
            self,
            message: types.Message,
            now: datetime,
            instruction_key: str,
    ) -> tuple[str, list[str]]:
        lines = []
        reply_user = None

        if message.reply_to_message:
            reply_user = message.reply_to_message.from_user

        if reply_user:
            target_user = reply_user
            _, user_date, log_texts = await self.user_service.get_user_date(
                telegram_user=reply_user,
                chat_id=message.chat.id,
            )
        else:
            target_user = self.user
            _, user_date, log_texts = await self.user_service.get_user_date(
                telegram_user=message.from_user,
                chat_id=message.chat.id,
            )

        if reply_user or user_date.pdr_date or user_date.period_date:
            user_full_name = html_secure(target_user.full_name.title())
            lines = [self.texts['user_head_text'].format(user_full_name), '']
            if user_date.pdr_date:
                lines.append(self.texts['pdr_text'].format(user_date.pdr_date.strftime('%d.%m.%Y')))
            else:
                lines.append(self.texts['pdr_unknown'])

            if user_date.period_date:
                period_text = texts_service.period_week_and_day(
                    texts=self.texts,
                    difference_seconds=int((now - user_date.period_date).total_seconds()),
                )
                lines.append(self.texts['period_text'].format(period_text))
            else:
                lines.append(self.texts['period_unknown'])

            if not user_date.pdr_date or not user_date.period_date:
                lines.append('')
                if not user_date.pdr_date:
                    if reply_user:
                        lines.append(
                            self.texts['pdr_instruction_reply'].format(user_full_name)
                        )
                    else:
                        lines.append(self.texts['pdr_instruction'])

                if not user_date.period_date:
                    period_instruction_text, example_weeks, example_days = (
                        self.get_example_period_instruction(now)
                    )
                    if reply_user:
                        lines.append(
                            self.texts['period_instruction_reply'].format(
                                user_full_name,
                                example_weeks,
                                example_days,
                            )
                        )
                    else:
                        lines.append(period_instruction_text)
        else:
            if 'period' in instruction_key:
                period_instruction_text, _, _ = self.get_example_period_instruction(now)
                lines.append(period_instruction_text)
            else:
                lines.append(self.texts[instruction_key])
        return '\n'.join(lines), log_texts


class UsersUpdater:
    @staticmethod
    async def check_users_exist_in_database() -> bool:
        """
        Checks if there are any user in the database.

        :return: True if there are user, False otherwise.
        :rtype: bool
        """
        async with UserRepository() as db:
            user = await db.get_any_user()
        return True if user else False

    async def update_users_in_database(self, spreadsheet: AsyncioGspreadSpreadsheet) -> None:
        """
        Updates user data and their dates in the database from Google Sheets.

        :param spreadsheet: The Google Sheets session for user notifications.
        """
        users_worksheet = await spreadsheet.worksheet(title=os.getenv('USERS_TABLE'))
        dates_worksheet = await spreadsheet.worksheet(title=os.getenv('USER_DATES_TABLE'))

        users_data = await users_worksheet.get('A1:Z50000', major_dimension='ROWS')
        dates_data = await dates_worksheet.get('A1:Z50000', major_dimension='ROWS')
        users = self.generate_users(users_data)
        dates = self.generate_dates(dates_data)
        async with UserRepository() as db_users:
            await db_users.sync_users(users)
        async with UserDateRepository() as db_dates:
            await db_dates.sync_dates(dates)

    @staticmethod
    def generate_users(data: list[list[str]]) -> list[User]:
        """
        Generates a list of User objects from raw data.

        :param data: The raw user data from the spreadsheet.
        :return: A list of User objects.
        :rtype: list[User]
        """
        google_row_id = 1
        response = []
        keys = list(map(str.strip, data.pop(0)))
        for row in data:
            google_row_id += 1
            if len(row) > 0:
                record = {}
                for key, value in zip(keys, row):
                    value = None if value == 'None' else value.strip()
                    record.update({key: value})
                user_id = re.sub(r'[^\d-]', '', record.get('id') or '')
                if user_id:
                    response.append(
                        User(
                            id=int(user_id),
                            full_name=record.get('full_name'),
                            username=record.get('username'),
                            language=record.get('lang'),
                            reaction=record.get('reaction') == '✅',
                            google_row_id=google_row_id,
                        )
                    )
        return response

    @staticmethod
    def generate_dates(data: list[list[str]]) -> list[UserDate]:
        """
        Generates a list of UserDate objects from raw dates data.

         :param data: The raw dates data from the spreadsheet.
         :return: A list of UserDate objects.
         :rtype: list[UserDate]
         """
        google_row_id = 1
        response = []
        keys = list(map(str.strip, data.pop(0)))
        for row in data:
            google_row_id += 1
            if len(row) > 1:
                record = {}
                for key, value in zip(keys, row):
                    value = None if value == 'None' else value.strip()
                    record.update({key: value})
                user_id = re.sub(r'[^\d-]', '', record.get('user_id') or '')
                if user_id:
                    pdr_date, period_date = None, None
                    if record.get('pdr_date'):
                        pdr_date = datetime.fromisoformat(record['pdr_date'])
                    if record.get('period_date'):
                        period_date = datetime.fromisoformat(record['period_date'])
                    response.append(
                        UserDate(
                            id=google_row_id,
                            user_id=int(user_id),
                            chat_id=record.get('chat_id'),
                            pdr_date=pdr_date,
                            period_date=period_date,
                        )
                    )
        return response

    @staticmethod
    async def back_up_users() -> None:
        """
        Backs up user data and dates from the database to Google Sheets.
        Extracts user data and their dates, and updates them in the corresponding Google Sheets.
        """
        async with UserRepository() as db_users:
            users = await db_users.get_users_to_backup()
            if users:
                spreadsheet = await google_session.get_spreadsheet(os.getenv('GOOGLE_SHEET_ID'))
                worksheet = await spreadsheet.worksheet(title=os.getenv('USERS_TABLE'))
                for user in users:
                    sheet_range = f'A{user.google_row_id}:E{user.google_row_id}'
                    try:
                        user_range = await worksheet.range(sheet_range)
                    except IndexError and Exception as error:
                        if 'exceeds grid limits' in str(error):
                            await worksheet.add_rows(1000)
                            await asyncio.sleep(1)
                            user_range = await worksheet.range(sheet_range)
                        else:
                            raise error

                    user_range[0].value = user.id
                    user_range[1].value = user.full_name
                    user_range[2].value = user.username or 'None'
                    user_range[3].value = user.language
                    user_range[4].value = '✅' if user.reaction else '🅾️'

                    await worksheet.update_cells(user_range)
                    await db_users.mark_user_as_synced(user)
                    backup_date = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' ', 'seconds')
                    logging.warning(f' {backup_date} BACKUP User {user.id}: SUCCESS')

        async with UserDateRepository() as db_dates:
            dates = await db_dates.get_dates_to_backup()
            if dates:
                spreadsheet = await google_session.get_spreadsheet(os.getenv('GOOGLE_SHEET_ID'))
                worksheet = await spreadsheet.worksheet(title=os.getenv('USER_DATES_TABLE'))
                for date in dates:
                    sheet_range = f'A{date.id}:D{date.id}'
                    pdr_date_text, period_date_text = 'None', 'None'
                    if date.pdr_date:
                        pdr_date_text = date.pdr_date.isoformat(' ', 'seconds')
                    if date.period_date:
                        period_date_text = date.period_date.isoformat(' ', 'seconds')

                    try:
                        date_range = await worksheet.range(sheet_range)
                    except IndexError and Exception as error:
                        if 'exceeds grid limits' in str(error):
                            await worksheet.add_rows(1000)
                            await asyncio.sleep(1)
                            date_range = await worksheet.range(sheet_range)
                        else:
                            raise error

                    date_range[0].value = date.user_id
                    date_range[1].value = date.chat_id
                    date_range[2].value = pdr_date_text
                    date_range[3].value = period_date_text

                    await worksheet.update_cells(date_range)
                    await db_dates.mark_date_as_synced(date)
                    backup_date = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' ', 'seconds')
                    logging.warning(f' {backup_date} BACKUP Date {date.id} {date.user_id}: SUCCESS')

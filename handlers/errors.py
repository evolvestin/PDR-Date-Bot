import os
import re
import sys
import logging
import traceback
from typing import Any
from aiogram import types
from services import Telegram
from datetime import datetime, timezone
from services.bot_instance import BotInstance
from functions.html import bold, code, italic, sub_tag, html_link, html_secure

sender = Telegram.MessageSender(link_preview=False)

IGNORE_ERRORS_PATTERN = '|'.join([
    'Backend Error',
    'Read timed out.', 'Message_id_invalid',
    'Connection aborted', 'ServerDisconnectedError',
    'Connection reset by peer', 'is currently unavailable.',
    'returned "Internal Error"', 'Message to forward not found',
    'Message can&#39;t be forwarded', 'Failed to establish a new connection',
    'The (read|write) operation timed out', 'EOF occurred in violation of protocol',
])


async def errors_handler(event: types.error_event.ErrorEvent) -> None:
    """
    Handles errors during bot event processing.

    Logs the error and triggers error reporting via TelegramError.

    :param event: The error event object containing details about the error.
    :type event: types.error_event.ErrorEvent
    """
    date = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(' ', 'seconds')
    logging.error(f' {date} Ошибка в обработке {event}')
    await TelegramError().handle_error(event)


def extract_error_details() -> tuple[str, list[str]]:
    """
    Extracts detailed information about the current exception.

    Formats the traceback and sanitizes it for safe HTML output.

    :return: A tuple containing the sanitized error text and the raw error details.
    :rtype: tuple[str, list[str]]
    """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    error_raw = traceback.format_exception(exc_type, exc_value, exc_traceback)
    return ''.join([html_secure(e) for e in error_raw]), error_raw


class TelegramError:
    """
    Singleton class for managing error reporting via Telegram.

    This class builds and sends error reports to a specified developer chat ID.
    """

    _instance = None  # Attribute to store the single class instance

    def __new__(cls, *args, **kwargs):
        """
        Ensures that only one instance of the class is created.

        :return: The single instance of the class.
        :rtype: TelegramError
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """
        Initializes the TelegramError instance.
        Sets up bot username, developer chat ID, and the message header.
        """
        if not hasattr(self, 'initialized'):  # Ensure initialization runs only once
            self.initialized = True
            self.bot_username = 'unknown_bot'
            self.dev_chat_id = int(os.getenv('ID_DEV', 0))
            self.header = self.build_header()  # Requires bot_username

    def update_dev_chat_id_from_environ(self):
        """Updates the developer chat ID from the environment variables"""
        self.dev_chat_id = int(os.getenv('ID_DEV', 0))

    def build_header(self) -> str:
        """
        Constructs a header for error messages.

        Includes the bot's username and hosting information (local/server).

        :return: The formatted header string.
        :rtype: str
        """
        link = self.bot_username
        host = 'local' if os.getenv('LOCAL') else 'server'
        if self.bot_username != 'unknown_bot':
            link = html_link(f'https://t.me/{self.bot_username}', self.bot_username)
        return f'{bold(link)} ({italic(host)})'

    async def update_header(self) -> None:
        """
        Updates the header with the bot's username.
        Fetches the bot username via the BotInstance if it is unknown.
        """
        if self.bot_username == 'unknown_bot':
            bot_me = await BotInstance().main_bot.get_me()
            self.bot_username = bot_me.username
            self.header = self.build_header()

    async def send_error_report(self, error: str, message: Any = None) -> None:
        """
        Sends an error report to the developer chat.

        Splits large error texts into multiple messages if necessary.

        :param error: The sanitized error message to be sent.
        :type error: str
        :param message: Additional context or data related to the error.
        :type message: Any, optional
        """
        caption, reply_id = None, None
        title = f'Вылет {self.header}:\n'
        len_error_text = len(sub_tag(title)) + len(error)

        if message:
            caption = f'{title}{code(error)}' if 0 < len_error_text <= 1024 else None
            file_name = f"error_report_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')}.json"
            file = types.BufferedInputFile(str(message).encode('utf-16-le'), filename=file_name)
            response = await sender.message(chat_id=self.dev_chat_id, file=file, text=caption)
            reply_id = response.message_id if response else reply_id

        if not caption:
            step = 4096 - len(sub_tag(title))
            for text in [error[i:i + step] for i in range(0, len(error), step)]:
                response = await sender.message(
                    chat_id=self.dev_chat_id,
                    text=f'{title}{code(text)}',
                    reply_id=reply_id,
                )
                title = ''
                reply_id = response.message_id if response else reply_id

    async def handle_error(self, message: Any = None) -> None:
        """
        Handles the current exception by reporting it.

        Extracts error details, logs them, and sends a detailed report.

        :param message: Additional context or data related to the error.
        :type message: Any, optional
        """
        error, error_raw = extract_error_details()
        try:
            logging.warning(f' Ошибка {error_raw[-1]}') if message is None else None
            if re.search(IGNORE_ERRORS_PATTERN, error):
                return

            await self.update_header()
            await self.send_error_report(error, message or '')
        except IndexError and Exception as short_error:
            more_error, _ = extract_error_details()
            error_text = (
                f'FIRST ERROR:\n\n'
                f'{error}\n\n'
                f'MORE SHORT ERROR: {short_error}\n'
                f'MORE ERROR:\n\n'
                f'{more_error}'
            )

            file = types.BufferedInputFile(error_text.encode('utf-16-le'), filename='error_report_fatal.json')
            await sender.message(chat_id=self.dev_chat_id, file=file, text='FATAL ERROR #fatal', raises=False)

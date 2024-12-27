import os
from aiogram import Bot


class BotInstance:
    """
    Singleton class for managing bot instances.

    This class ensures that there is a single instance of the bots used in the application.
    It provides methods to access and update the main and log bots based on environment variables.
    """
    _instance = None  # Attribute to store the single class instance

    def __new__(cls, *args, **kwargs):
        """
        Ensures that only one instance of the class is created.

        :return: The singleton instance of the class.
        :rtype: BotInstance
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """Initializes the bot instances based on environment variables"""
        if not hasattr(self, '_main_bot'):
            self._main_bot = Bot(token=os.getenv('MAIN_TOKEN'))
        if not hasattr(self, '_log_bot'):
            if os.getenv('LOG_TOKEN'):
                self._log_bot = Bot(token=os.getenv('LOG_TOKEN'))
            else:
                self._log_bot = self._main_bot

    def update_bot_tokens_from_environ(self) -> None:
        """
        Updates the bot tokens based on current environment variables.
        If the tokens in the environment differ from the current tokens, the bot instances are recreated.
        """
        # Update the main bot if the token has changed
        if os.getenv('MAIN_TOKEN') != self._main_bot.token:
            self._main_bot = Bot(token=os.getenv('MAIN_TOKEN'))

        # Update the log bot if the token has changed
        if os.getenv('LOG_TOKEN') != self._log_bot.token:
            if os.getenv('LOG_TOKEN'):
                self._log_bot = Bot(token=os.getenv('LOG_TOKEN'))
            else:
                self._log_bot = self._main_bot

    @property
    def log_bot(self) -> Bot:
        """
        Accessor for the log bot instance.

        :return: The bot instance used for logging.
        :rtype: Bot
        """
        return self._log_bot

    @property
    def main_bot(self) -> Bot:
        """
        Accessor for the main bot instance.

        :return: The bot instance used for primary operations.
        :rtype: Bot
        """
        return self._main_bot

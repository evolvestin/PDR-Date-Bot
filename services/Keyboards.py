from typing import Union
from services import Texts
from database.models import User
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup

texts_service = Texts.TextsService()


class Keys:
    def __init__(self, user: User, texts: dict[str, str]):
        """
        Initializes the Keys class with the user's data and texts.

        :param user: The user object for whom the keyboard is being created.
        :type user: User
        :param texts: A dictionary containing text data for various keys.
        :type texts: dict[str, str]
        """
        self.user: User = user
        self.texts: dict[str, str] = texts
        self.button = InlineKeyboardButton

    @staticmethod
    def get_keyboard(
            values: Union[list, InlineKeyboardButton] = None,
            inline: bool = True,
            row_width: int = 2
    ) -> InlineKeyboardMarkup | ReplyKeyboardMarkup:
        """
        Creates an inline or reply keyboard based on the provided values.

        :param values: A list of InlineKeyboardButtons or a single button to be added to the keyboard.
        :type values: Union[list, InlineKeyboardButton]
        :param inline: A flag indicating whether the keyboard is inline or not.
        :type inline: bool
        :param row_width: The number of buttons per row.
        :type row_width: int
        :return: A markup representing the generated keyboard.
        :rtype: InlineKeyboardMarkup | ReplyKeyboardMarkup
        """
        builder = InlineKeyboardBuilder() if inline else ReplyKeyboardBuilder()
        if values:
            builder.add(*values) if type(values) is list else builder.add(*[values])
            builder = builder.adjust(row_width, repeat=True)
        return builder.as_markup()

    def choose_gender(self):
        buttons = [
            self.button(text=self.texts['baby_male_button'], callback_data='baby_gender_male'),
            self.button(text=self.texts['baby_female_button'], callback_data='baby_gender_female'),
        ]
        return self.get_keyboard(buttons)

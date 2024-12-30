from aiogram import types
from functions.html import code
from database.models import User
from services import Keyboards, Logger, Telegram, Texts, Users


sender = Telegram.MessageSender()
user_service = Users.UserService()
texts_service = Texts.TextsService()
logger_service = Logger.TelegramLogger()


async def callback_handler(call: types.CallbackQuery) -> None:
    """
    Handles callback queries triggered by inline button clicks.

    :param call: Callback query data
    :type call: types.CallbackQuery
    """
    user, texts, log_texts = await user_service.get_user(call)
    user_callback_handler = UserCallbackHandler(user, texts, call)

    if isinstance(call.message, types.InaccessibleMessage):
        await sender.answer(call_id=call.id, text=texts['callback_error'], alert=True)

    if call.data.startswith('baby_gender'):
        log_texts.append(await user_callback_handler.baby_gender_handler())

    await logger_service.log_text_handler(call, log_text='\n'.join(log_texts))


class UserCallbackHandler:
    """
    Handles user-specific callback actions.

    :param user: The user associated with the callback.
    :type user: User
    :param texts: Localized text for user messages.
    :type texts: dict[str, str]
    :param call: The callback query being processed.
    :type call: types.CallbackQuery
    """

    def __init__(self, user: User, texts: dict[str, str], call: types.CallbackQuery):
        """Initializes the UserCallbackHandler with user data and callback query details"""
        self.user: User = user
        self.texts: dict[str, str] = texts
        self.call: types.CallbackQuery = call
        self.keys = Keyboards.Keys(user, texts)
        self.user_text_service = Users.UserTextGenerator(user=user, texts=texts, keys=self.keys)

        # Set reply markup if available
        if isinstance(call.message, types.Message):
            self.reply_markup: types.InlineKeyboardMarkup = call.message.reply_markup
        else:
            self.reply_markup = None

    async def baby_gender_handler(self):
        gender_id = 1
        reply_user = self.user
        gender_text_key = 'baby_male_button'
        if 'female' in self.call.data:
            gender_id = 2
            gender_text_key = 'baby_female_button'

        log_text = f'Выбрал пол ребенка {self.texts[gender_text_key]} (id:{code(gender_id)})'

        if self.call.message.reply_to_message:
            reply_user = self.call.message.reply_to_message.from_user

        if self.user.id == reply_user.id:
            edit_message = None
            text = self.texts['gender_updated'].format(self.user.full_name.title(), self.texts[gender_text_key])

            if self.call.message.chat.id > 0:
                edit_message = self.call.message

            await sender.answer(call_id=self.call.id)
            await user_service.update_user_baby_gender(
                gender_id=gender_id,
                user_id=self.user.id,
                chat_id=self.call.message.chat.id,
            )
            await sender.message(chat_id=self.call.message.chat.id,  text=text, edit_message=edit_message)
            await user_service.delete_chat_message(message=self.call.message, delete_reply=True)
        else:
            await sender.answer(call_id=self.call.id, text=self.texts['error_outer_interrupt'], alert=True)
            log_text += ', но это не его вызов команды #outer_interrupt'
        return log_text

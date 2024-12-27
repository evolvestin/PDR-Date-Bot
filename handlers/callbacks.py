from aiogram import types
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
    # user_callback_handler = UserCallbackHandler(user, texts, call)

    if isinstance(call.message, types.InaccessibleMessage):
        await sender.answer(call_id=call.id, text=texts['callback_error'], alert=True)

    # if call.data.startswith(''):
        # log_texts.append(await user_callback_handler.function())

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

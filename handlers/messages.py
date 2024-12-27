import os
from aiogram import types
from services import Logger, Telegram, Texts, Users

sender = Telegram.MessageSender()
user_service = Users.UserService()
texts_service = Texts.TextsService()
logger_service = Logger.TelegramLogger()


async def chat_action_handler(message: types.Message) -> None:
    """
    Handles chat action events such as chat migrations and logging.

    :param message: Telegram message object containing the chat action details.
    :type message: types.Message
    """
    user, _, log_texts = await user_service.get_user(message)
    if message.migrate_to_chat_id:
        await user_service.disable_chat_user(user)
    await logger_service.log_text_handler(message, log_text='\n'.join(log_texts))


async def member_handler(message: types.ChatMemberUpdated):
    """
    Handles member updates such as reactions and logging.

    :param message: Telegram ChatMemberUpdated object containing member update details.
    :type message: types.ChatMemberUpdated
    """
    user, texts, log_texts = await user_service.get_user(message)

    reaction, chat_greeting = await user_service.get_reaction(message)
    if reaction is not None:
        await user_service.update_user_reaction(user, reaction)
    if chat_greeting:
        await sender.message(chat_id=message.chat.id, text=texts['start_text'])

    await logger_service.log_text_handler(message, log_text='\n'.join(log_texts))


async def media_message_handler(message: types.Message) -> None:
    """
    Handles incoming media messages, retrieves file IDs for admins, or forwards messages.

    :param message: Telegram message object containing media content.
    :type message: types.Message
    """
    _, _, log_texts = await user_service.get_user(message)
    await sender.message(
        chat_id=int(os.getenv('ID_DUMP')),
        from_chat_id=message.chat.id,
        forward_id=message.message_id,
    )
    await logger_service.log_text_handler(message, log_text='\n'.join(log_texts))


async def bot_text_message_handler(message: types.Message) -> None:
    """
    Processes text messages, identifies relevant lots, and generates appropriate responses.

    :param message: Telegram message object containing text data.
    :type message: types.Message
    """
    _, _, log_texts = await user_service.get_user(message)

    await sender.message(
        chat_id=int(os.getenv('ID_DUMP')),
        from_chat_id=message.chat.id,
        forward_id=message.message_id,
    )
    await logger_service.log_text_handler(message, log_text='\n'.join(log_texts))

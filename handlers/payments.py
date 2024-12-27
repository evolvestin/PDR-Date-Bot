import os
from aiogram import types
from services import Users, Logger, Telegram

sender = Telegram.MessageSender()
user_service = Users.UserService()
logger_service = Logger.TelegramLogger()


async def pre_checkout_handler(event: types.PreCheckoutQuery) -> None:
    """
    Responds to a pre-checkout query in a payment process.

    This function confirms the pre-checkout query to proceed with the payment process.

    :param event: The pre-checkout query event containing information about the payment.
    :type event: types.PreCheckoutQuery
    """
    await event.answer(ok=True)


async def successful_payment_handler(message: types.Message) -> None:
    """
    Handles the successful payment event.

    This function performs the following actions when a payment is successfully processed:
    - Retrieves user data and sends a success message to the user.
    - Logs details of the successful payment for internal tracking.
    - Sends a notification about the payment to the developer chat.

    :param message: The message event containing information about the successful payment.
    :type message: types.Message
    """
    user, texts, log_texts = await user_service.get_user(message)
    await sender.message(chat_id=message.chat.id, text=texts['donate_success'], reply_id=message.message_id)

    lines = [f'{logger_service.get_header(message.chat, message.date)}:']
    currency_text = '⭐️' if message.successful_payment.currency else message.successful_payment.currency

    if message.chat.id < 0 and message.from_user:
        lines.append(f'👤 {logger_service.get_header(message.from_user)}:')

    lines.extend([
        '🍩 Donation 🍩',
        f'Amount: {message.successful_payment.total_amount} {currency_text}',
        f'Charge ID: {message.successful_payment.telegram_payment_charge_id}',
    ])

    await sender.message(
        chat_id=int(os.environ['ID_DEV']),
        text='\n'.join(lines)
    )

    await logger_service.log_text_handler(message, log_text='\n'.join(log_texts))

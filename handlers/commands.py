import os
import re
import math
import random
from aiogram import types
from functions.html import code
from database.models import User
from datetime import datetime, timedelta
from services.bot_instance import BotInstance
from services import google_client, Keyboards, Users, Logger, Telegram, Texts


sender = Telegram.MessageSender()
user_service = Users.UserService()
texts_service = Texts.TextsService()
logger_service = Logger.TelegramLogger()
google_session = google_client.GoogleSheetsSession()


async def bot_command_handler(message: types.Message) -> None:
    """
    Handles incoming bot commands and delegates them to the appropriate command handlers.

    This function processes user commands sent to the bot and routes them to the corresponding
    handlers based on the command type.
    If the command is not recognized, it forwards the message to a predefined dump channel.

    :param message: Incoming message from a Telegram user.
    :type message: types.Message
    """
    command_not_recognized = False
    message_text = message.text.lower()
    user, texts, log_texts = await user_service.get_user(message)
    user_commands = GeneralCommands(user, texts, message)

    if message_text.startswith('/pdr'):
        log_texts.extend(await user_commands.pdr_command_handler())
    elif message_text.startswith('/period'):
        log_texts.extend(await user_commands.period_command_handler())
    elif message_text.startswith('/gender'):
        await user_commands.gender_command_handler()
    elif message_text.startswith('/id'):
        await user_commands.id_command_handler()
    elif message_text.startswith(('/start', '/help')):
        await user_commands.start_command_handler()
    elif message_text.startswith('/donate'):
        await user_commands.donate_command_handler()

    elif str(user.id) in os.getenv('ADMINS'):
        admin_commands = AdminCommands(user, texts, message)
        if message_text.startswith('/update_texts'):
            await admin_commands.update_texts_command_handler()
        else:
            command_not_recognized = True
    else:
        command_not_recognized = True

    if command_not_recognized:
        log_texts.append('[Команды не существует]')
        await sender.message(
            chat_id=int(os.getenv('ID_DUMP')),
            from_chat_id=message.chat.id,
            forward_id=message.message_id,
        )
    await user_service.set_commands(chat_id=message.chat.id, texts=texts)
    await logger_service.log_text_handler(message, log_text='\n'.join(log_texts))


class AdminCommands:
    """
    Handles administrative commands.

    :param user: The user object associated with the command.
    :type user: User
    :param texts: A dictionary containing localized text strings.
    :type texts: dict[str, str]
    :param message: The incoming message object.
    :type message: types.Message
    """

    def __init__(self, user: User, texts: dict[str, str], message: types.Message):
        """Initializes the AdminCommands class with user data, localized texts, and message information"""
        self.user: User = user
        self.texts: dict[str, str] = texts
        self.message: types.Message = message
        self.keys: Keyboards.Keys = Keyboards.Keys(user, texts)
        self.user_text_service = Users.UserTextGenerator(
            user=user,
            texts=texts,
            keys=self.keys,
            message_text=message.text.lower(),
        )

    async def update_texts_command_handler(self) -> None:
        """
        Handles the command to update text entries in the local database.

        This function fetches the latest spreadsheet data from Google Sheets,
        updates the local database with new or modified texts, and sends a confirmation
        message to the user.
        """
        spreadsheet = await google_session.get_spreadsheet(os.getenv('GOOGLE_SHEET_ID'))
        text = await Texts.TextsUpdater().update_texts_in_local_database(spreadsheet)
        await sender.message(chat_id=self.message.chat.id, text=text)


class GeneralCommands:
    """
    Initializes the GeneralCommands class with user data and message context.

    :param user: The user interacting with the bot.
    :type user: User
    :param texts: Localized text dictionary for generating responses.
    :type texts: dict[str, str]
    :param message: The message object containing user input.
    :type message: types.Message
    """

    def __init__(self, user: User, texts: dict[str, str], message: types.Message):
        self.user: User = user
        self.texts: dict[str, str] = texts
        self.message: types.Message = message
        self.keys: Keyboards.Keys = Keyboards.Keys(user, texts)
        self.user_text_service = Users.UserTextGenerator(
            user=user,
            texts=texts,
            keys=self.keys,
            message_text=message.text.lower(),
        )

    async def start_command_handler(self) -> None:
        """
        Handles the '/start' command to initialize the bot for a new user.
        Sends a welcome message, sets user commands.
        """
        await sender.message(
            chat_id=self.message.chat.id,
            text=self.texts['start_text'],
            reply_id=self.message.message_id,
        )
        await user_service.set_commands(chat_id=self.message.chat.id, texts=self.texts)

    async def donate_command_handler(self) -> None:
        """
        Handles the '/donate' command to facilitate donations.
        Calculates a suggested donation amount and sends an invoice to the user.
        """
        multiplier = random.uniform(2, 3)
        amount, max_star_donation = 100, 100000
        data = re.sub(r'\D', '', self.user_text_service.message_text)
        suggested_amount = max_star_donation

        if data and 0 < int(data) <= max_star_donation:
            amount = int(data)
        if amount * multiplier < max_star_donation:
            suggested_amount = amount * multiplier

        await BotInstance().main_bot.send_invoice(
            chat_id=self.message.chat.id,
            title=self.texts['donate_title'],
            description=self.texts['donate_description'].format(math.ceil(suggested_amount)),
            payload='donate',
            currency='XTR',
            prices=[types.LabeledPrice(label='XTR', amount=amount)],
            reply_to_message_id=self.message.message_id,
        )

    async def id_command_handler(self) -> None:
        """
        Handles the '/id' command to retrieve user or chat IDs.

        Sends a message containing the ID of the user, chat, or replied-to user/bot.
        """
        if self.message.reply_to_message:
            reply = self.message.reply_to_message.from_user
            user_text_key = 'user_type_bot' if reply.is_bot else self.texts['user_type_user']
            lines = [
                logger_service.get_header(chat=reply),
                f'ID: {code(reply.id)}',
                self.texts['user_type'].format(self.texts[user_text_key]),
            ]
        else:
            lines = [self.texts['your_id'].format(self.message.from_user.id)]
            if self.message.chat.id < 0:
                lines.append(self.texts['chat_id'].format(self.message.chat.id))
        await sender.message(chat_id=self.message.chat.id, text='\n'.join(lines), reply_id=self.message.message_id)

    async def gender_command_handler(self) -> None:
        reply_id = None
        keyboard = self.keys.choose_gender()
        text = self.texts['gender_private_instruction']
        if self.message.chat.type != 'private':
            reply_id = self.message.message_id
            text = self.texts['gender_chat_instruction'].format(self.user.full_name.title())
        await sender.message(chat_id=self.message.chat.id, text=text, keyboard=keyboard, reply_id=reply_id)

    async def pdr_command_handler(self) -> list[str]:
        await user_service.update_variable_bot_username()
        reply_id = self.message.message_id
        if self.user_text_service.message_text in ['/pdr', f'/pdr@{user_service.bot_username}'.lower()]:
            deleted = await user_service.delete_chat_message(message=self.message, delete_reply=False)
            if deleted:
                reply_id = None
            text, log_texts = await self.user_text_service.get_user_complete_info(
                message=self.message,
                now=user_service.get_now(),
                instruction_key='pdr_instruction',
            )
        else:
            log_texts = []
            data = re.sub('/[a-z]', '', self.user_text_service.message_text).strip()
            data = re.sub(r'\D+', '-', data).strip('-')
            search = re.search(r'(\d{2})-(\d{2})-(\d{2,4})', data)
            if search:
                year = f'20{search.group(3)[:2]}' if len(search.group(3)) < 4 else search.group(3)
                user_pdr_date = datetime.fromisoformat(f'{year}-{search.group(2)}-{search.group(1)} 00:00:00')
                await user_service.update_user_pdr_date(
                    user_id=self.user.id,
                    chat_id=self.message.chat.id,
                    date=user_pdr_date,
                )
                text = self.texts['pdr_updated'].format(self.user.full_name, user_pdr_date.strftime('%d.%m.%Y'))
            else:
                text_parts = [
                    self.texts['pdr_not_recognized'],
                    self.texts['pdr_instruction'],
                ]
                text = '\n\n'.join(text_parts)

        await sender.message(chat_id=self.message.chat.id, text=text, reply_id=reply_id)
        return log_texts

    async def period_command_handler(self) -> list[str]:
        await user_service.update_variable_bot_username()
        now = user_service.get_now()
        reply_id = self.message.message_id
        if self.user_text_service.message_text in ['/period', f'/period@{user_service.bot_username}'.lower()]:
            deleted = await user_service.delete_chat_message(message=self.message, delete_reply=False)
            if deleted:
                reply_id = None

            text, log_texts = await self.user_text_service.get_user_complete_info(
                now=now,
                message=self.message,
                instruction_key='period_instruction',
            )
        else:
            log_texts = []
            data = re.sub('/[a-z]', '', self.user_text_service.message_text).strip()
            data = re.sub(r'\D+', '-', data).strip('-')
            split = data.split('-')
            if len(split) >= 1 and split[0]:
                weeks = int(split[0])
                days = int(split[1]) if len(split) >= 2 else 0
                raw_user_period = now - timedelta(weeks=weeks, days=days)
                user_period = datetime.fromisoformat(raw_user_period.strftime('%Y-%m-%d 00:00:00'))
                await user_service.update_user_period_date(
                    user_id=self.user.id,
                    chat_id=self.message.chat.id,
                    date=user_period,
                )
                period_text = texts_service.period_week_and_day(
                    texts=self.texts,
                    difference_seconds=int((now - user_period).total_seconds()),
                )
                text = self.texts['period_updated'].format(self.user.full_name, period_text)
            else:
                period_instruction_text, _, _ = self.user_text_service.get_example_period_instruction(now)
                text_parts = [
                    self.texts['period_not_recognized'],
                    period_instruction_text,
                ]
                text = '\n\n'.join(text_parts)

        await sender.message(chat_id=self.message.chat.id, text=text, reply_id=reply_id)
        return log_texts

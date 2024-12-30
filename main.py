import asyncio
import logging
from aiogram.filters import or_f
from datetime import datetime, timezone
from aiogram import Dispatcher, Router, F
from services.bot_instance import BotInstance
from database import session as database_session
from database.models import Log, Texts, User, UserPregnancy
from handlers import loops, callbacks, commands, errors, messages, payments

task_handlers = loops.TaskHandlers()
logging.basicConfig(level=logging.INFO)


def run_background_tasks():
    """Launch background tasks required for the bot's operation"""
    asyncio.create_task(task_handlers.run_task(function=task_handlers.scheduled_actions))
    asyncio.create_task(task_handlers.run_task(function=task_handlers.logger_queue_handler))


def register_router() -> Router:
    """
    Registers all the bot's handlers for different types of messages and events.

    This function registers the following handlers:
    - Handler for user chat member changes (added/blocked).
    - Error handler.
    - Handler for callback queries (button presses).
    - Pre-checkout query handler for user payments.
    - Handler for various chat actions (e.g., pinned message, new chat title).
    - Media message handler (e.g., audio, photo, video).
    - Command handler for bot commands (e.g., '/start', '/lots', '/sub').
    - Handler for regular text messages.

    :return: The router with all the registered handlers.
    :rtype: Router
    """
    router = Router()

    # Handler for chat member changes (added/blocked)
    router.my_chat_member.register(messages.member_handler)
    router.chat_member.register(messages.member_handler)

    # Error handler
    router.errors.register(errors.errors_handler)

    # Handler for callback query
    router.callback_query.register(callbacks.callback_handler)

    # Pre-checkout query handler for payments
    router.pre_checkout_query.register(payments.pre_checkout_handler)

    # Handler for chat action messages
    router.message.register(messages.chat_action_handler, or_f(
        F.pinned_message,
        F.new_chat_title,
        F.delete_chat_photo,
        F.group_chat_created,
        F.migrate_to_chat_id,
        F.migrate_from_chat_id,
    ))

    # Handler for media messages
    router.message.register(messages.media_message_handler, or_f(
        F.dice,
        F.game,
        F.poll,
        F.audio,
        F.photo,
        F.voice,
        F.video,
        F.contact,
        F.sticker,
        F.document,
        F.location,
        F.animation,
        F.video_note,
        F.new_chat_photo,
    ))

    # Command handler
    router.message.register(commands.bot_command_handler, F.text.startswith('/'))

    # Handler for regular text messages
    router.message.register(messages.bot_text_message_handler, F.text)
    return router


async def main():
    """
    Initializes the database, registers the handlers, and starts the bot.

    This function performs the following tasks:
    - Records the start time of the application.
    - Initializes the necessary databases (Postgres and SQLite).
    - Registers all the bot handlers.
    - Initializes constants used by the bot.
    - Starts background tasks for logging, database backups, and notifications.
    - Starts the bot's polling loop to handle incoming messages.
    """
    # Save the start date and time of the application
    start_time = datetime.now(timezone.utc)

    # Initialize the databases
    await database_session.init_database(
        postgres_tables=[User.__tablename__, UserPregnancy.__tablename__],
        sqlite_tables=[Log.__tablename__, Texts.__tablename__],
    )

    # Register handlers
    dispatcher = Dispatcher()
    router = register_router()
    dispatcher.include_router(router)

    # Initialize constants
    await task_handlers.init_constants(start_time)

    # Start background tasks
    run_background_tasks()

    # Start the bot
    await dispatcher.start_polling(BotInstance().main_bot)


if __name__ == '__main__':
    asyncio.run(main())

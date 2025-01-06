import os
import re
import json
import asyncio
from aiogram import types
from services import Telegram
from typing import Optional, Union
from collections import defaultdict
from services.bot_instance import BotInstance
from database.log_repository import LogRepository
from datetime import datetime, timezone, timedelta
from functions.html import bold, code, sub_tag, html_link, blockquote, html_secure

LOGS_CUTOFF = 50000
main_sender = Telegram.MessageSender(use_main_bot=True, link_preview=False)
log_sender = Telegram.MessageSender(use_main_bot=False, link_preview=False)
RU_WEEK = {'Mon': 'Пн', 'Tue': 'Вт', 'Wed': 'Ср', 'Thu': 'Чт', 'Fri': 'Пт', 'Sat': 'Сб', 'Sun': 'Вс'}


class EntitiesToHTML:
    """
    Handles the conversion of message entities into HTML tags for formatting purposes.

    :param message: Telegram message object containing text and entities to convert.
    :type message: types.Message
    """
    def __init__(self, message: types.Message):
        self.message: types.Message = message

    @staticmethod
    def generate_html_tags(entity: types.MessageEntity) -> tuple[str, str]:
        """
        Generates HTML tags corresponding to the type of message entity.

        :param entity: A single message entity with type and optional language.
        :type entity: types.MessageEntity

        :return: A tuple containing the opening and closing HTML tags.
        :rtype: tuple[str, str]
        """

        # Handle preformatted text with optional language class
        if entity.type == 'pre':
            if entity.language:
                return f'<pre><code class="language-{entity.language}">', '</code></pre>'
            else:
                return '<pre>', '</pre>'

        # Ignore certain entity types
        if entity.type in ['url', 'email', 'cashtag', 'hashtag', 'mention', 'phone_number', 'text_mention']:
            return '', ''

        # Map entity types to HTML tags
        html_tags_by_type = {
            'bold': ('<b>', '</b>'),
            'italic': ('<i>', '</i>'),
            'underline': ('<u>', '</u>'),
            'code': ('<code>', '</code>'),
            'strikethrough': ('<s>', '</s>'),
            'spoiler': ('<tg-spoiler>', '</tg-spoiler>'),
            'blockquote': ('<blockquote>', '</blockquote>'),
            'text_link': (f'<a href="{entity.url}">', '</a>'),
            'expandable_blockquote': ('<blockquote expandable>', '</blockquote>'),
        }
        # Default to code tags for unknown types
        return html_tags_by_type.get(entity.type) or html_tags_by_type['code']

    def convert(self) -> str:
        """
        Converts message text and entities into an HTML-formatted string.

        :return: The message text with HTML tags applied to entities.
        :rtype: str
        """
        entities = self.message.entities or self.message.caption_entities
        text_list = list(self.message.text or self.message.caption or [])
        if entities:
            position = 0
            for entity in text_list:
                true_length = len(entity.encode('utf-16-le')) // 2
                while true_length > 1:
                    text_list.insert(position + 1, '')
                    true_length -= 1
                position += 1
            for entity in reversed(entities):
                end_index = entity.offset + entity.length - 1
                if entity.offset + entity.length >= len(text_list):
                    end_index = len(text_list) - 1

                tag_start, tag_end = self.generate_html_tags(entity)
                text_list[entity.offset] = f'{tag_start}{text_list[entity.offset]}'
                text_list[end_index] += tag_end
        return ''.join(text_list)


class ChatMemberLogHandler:
    """
    Handles logging of chat member updates in Telegram chats.

    This class processes changes in the status or permissions of chat members and generates
    appropriate log messages based on the type of change.

    :param message: The chat member update message from Telegram.
    :type message: types.ChatMemberUpdated
    """
    def __init__(self, message: types.ChatMemberUpdated):
        self.message: types.ChatMemberUpdated = message
        self.old_member = message.old_chat_member
        self.new_member = message.new_chat_member
        self.old_status = message.old_chat_member.status
        self.new_status = message.new_chat_member.status
        self.ru_user_type = 'бота' if message.new_chat_member.user.is_bot else 'пользователя'
        self.ru_chat_type = 'канал' if message.chat.type == 'channel' else 'чат'

    def get_action_for_old_member(self) -> tuple[str, str]:
        """
        Determines the action taken on the old member based on their status.

        :return: A tuple containing a descriptive message and the action keyword.
        :rtype: tuple[str, str]
        """
        if self.old_status in ['left', 'kicked']:
            if self.message.chat.id < 0:
                return self.handle_chat_entry_or_kick()
            return f'Разблокировал {self.ru_user_type}', 'unblocked'
        else:
            if self.message.chat.id < 0:
                return self.handle_chat_removal_or_change()
            return f'Заблокировал {self.ru_user_type}', 'block'

    def handle_chat_entry_or_kick(self) -> tuple[str, str]:
        """
        Handles actions related to entering or being kicked from a chat.

        :return: A tuple containing a descriptive message and the action keyword.
        :rtype: tuple[str, str]
        """
        if self.new_status == 'left':
            return f'Разрешил вход {self.ru_user_type} в {self.ru_chat_type}', 'changed'
        elif self.new_status == 'kicked':
            return f'Запретил вход {self.ru_user_type} в {self.ru_chat_type}', 'changed'
        elif self.new_status == 'administrator':
            return f'Добавил {self.ru_user_type} как админа в {self.ru_chat_type}', 'added'
        return f'Добавил {self.ru_user_type} в {self.ru_chat_type}', 'added'

    def handle_chat_removal_or_change(self) -> tuple[str, str]:
        """
        Handles actions related to removal or status change within a chat.

        :return: A tuple containing a descriptive message and the action keyword.
        :rtype: tuple[str, str]
        """
        # If the user left or was removed from the chat
        if self.new_status in ['left', 'kicked']:
            admin = '-админа' if self.old_status == 'administrator' else ''
            return f'Удалил {self.ru_user_type}{admin} из {self.ru_chat_type}а', 'kicked'

        # If the status changed within administration
        elif self.old_status == 'administrator' and self.new_status == 'administrator':
            return f'Изменил {self.ru_user_type} как админа в {self.ru_chat_type}е', 'changed'

        # If the new status is administrator
        elif self.new_status == 'administrator':
            return f'Назначил {self.ru_user_type} админом в {self.ru_chat_type}е', 'changed'

        # If restrictions for the user are updated
        elif self.old_status == 'restricted' and self.new_status == 'restricted':
            return f'Изменил ограничения {self.ru_user_type} в {self.ru_chat_type}е', 'changed'

        # If restrictions for the user are lifted
        elif self.old_status == 'restricted' and self.new_status != 'restricted':
            return f'Снял ограничения {self.ru_user_type} в {self.ru_chat_type}е', 'changed'

        # If the user received restrictions
        elif self.new_status == 'restricted':
            return f'Ограничил {self.ru_user_type} в {self.ru_chat_type}е', 'changed'

        return f'Забрал роль админа у {self.ru_user_type} в {self.ru_chat_type}е', 'changed'

    def compare_permissions(self) -> str:
        """
        Compares old and new permissions of the chat member and generates a summary of changes.

        :return: A formatted string describing the permission changes, if any.
        :rtype: str
        """
        changes = []
        permissions = {
            # ChatMemberAdministrator permissions
            'can_manage_chat': f'управлять {self.ru_user_type}ом',

            'can_post_messages': 'отправлять сообщения',
            'can_edit_messages': 'редактировать сообщения',
            'can_delete_messages': 'удалять сообщения',

            'can_restrict_members': 'банить пользователей',

            'can_post_stories': 'публиковать истории',
            'can_edit_stories': 'редактировать истории',
            'can_delete_stories': 'удалять истории',

            'can_manage_video_chats': 'управлять видео чатами',
            'can_promote_members': 'назначать пользователей админом',

            'can_manage_voice_chats': 'управлять голосовыми чатами',
            'can_be_edited': f'бот редактировать этого {self.ru_user_type}',

            # ChatMemberRestricted permissions
            'can_send_messages': 'отправлять сообщения',

            'can_send_photos': 'отправлять фотографии',
            'can_send_videos': 'отправлять видео',
            'can_send_video_notes': 'отправлять видео-сообщение',
            'can_send_audios': 'отправлять аудио',
            'can_send_voice_notes': 'отправлять голосовые сообщения',
            'can_send_documents': 'отправлять документы',
            'can_send_other_messages': 'отправлять стикеры и анимации',
            'can_send_media_messages': 'отправлять медиа сообщения',
            'can_add_web_page_previews': 'добавлять пред-просмотры ссылок',
            'can_send_polls': 'отправлять опросы',

            # General
            'can_invite_users': 'добавлять пользователей',
            'can_manage_topics': 'управлять темами форума',
            'can_pin_messages': 'закреплять сообщения',
            'can_change_info': f'изменять информацию о {self.ru_chat_type}е',

        }
        if self.old_status == self.new_status:
            for permission, description in permissions.items():
                old_value = getattr(self.message.old_chat_member, permission, None)
                new_value = getattr(self.message.new_chat_member, permission, None)
                if old_value is not None and new_value is not None and old_value != new_value:
                    changes.append(bold(f"{'Разрешил' if new_value else 'Запретил'} {description} #{permission}"))

        elif self.new_status == 'administrator' or self.new_status == 'restricted':
            for permission, description in permissions.items():
                new_value = getattr(self.message.new_chat_member, permission, None)
                if new_value is not None:
                    changes.append(bold(f"{'Может' if new_value else 'Не может'} {description} #{permission}"))

        return '\n'.join(changes) or ''

    def handle_self_action(self) -> tuple[str, str]:
        """
        Handles actions performed by the bot on itself.

        :return: A tuple containing a descriptive message and the action keyword.
        :rtype: tuple[str, str]
        """
        if self.old_status in ['left', 'kicked']:
            return f'Зашел в {self.ru_chat_type} по ссылке', 'added'
        return f'Вышел из {self.ru_chat_type}а', 'left'


class ProcessMessage:
    """
    Handles processing of various types of messages in Telegram.

    This class extracts information about media files, actions, and events within a chat,
    providing structured descriptions for logging or further processing.

    :param message: The Telegram message object to process.
    :type message: types.Message
    """
    def __init__(self, message: types.Message):
        self.message: types.Message = message

    def get_media_file_id_and_description(self) -> tuple[Optional[str], str]:
        """
        Retrieves the file ID and a description for various types of media in the message.

        This method checks the message for different media types (e.g., photo, video, document)
        and returns the corresponding file ID and a descriptive text.

        :return: A tuple containing the file ID (if applicable) and a description of the media.
        :rtype: tuple[Optional[str], str]
        """
        if self.message.photo:
            return self.message.photo[-1].file_id, f"{bold('Отправил фото')} #photo"
        elif self.message.new_chat_photo:
            return self.message.new_chat_photo[-1].file_id, f"{bold('Изменил аватар чата')} #new_chat_photo"
        elif self.message.animation:
            return self.message.animation.file_id, f"{bold('Отправил анимацию')} #gif #animation"
        elif self.message.document:
            return self.message.document.file_id, f"{bold('Отправил документ')} #document"
        elif self.message.voice:
            return self.message.voice.file_id, f"{bold('Отправил голосовое сообщение')} #voice"
        elif self.message.audio:
            return self.message.audio.file_id, f"{bold('Отправил аудиофайл')} #audio"
        elif self.message.video:
            return self.message.video.file_id, f"{bold('Отправил видео')} #video"
        elif self.message.video_note:
            return self.message.video_note.file_id, f"{bold('Отправил видео-сообщение')} #video_note"
        elif self.message.sticker:
            return self.message.sticker.file_id, f"{bold('Отправил стикер')} #sticker"
        elif self.message.paid_media:
            return None, f"{bold(f'Отправил платный медиа')} за {self.message.paid_media.star_count}⭐ #paid_media"
        elif self.message.story:
            return None, f"{bold('Опубликовал историю')} #story"
        elif self.message.dice:
            return None, f"{bold('Отправил дайс')} {self.message.dice.emoji}: {self.message.dice.value} #dice"
        elif self.message.poll:
            return None, f"Создал {bold('викторину' if self.message.poll.type == 'quiz' else 'голосование')} #poll"
        elif self.message.location:
            return None, f"{bold('Отправил локацию')} #location"
        elif self.message.venue:
            return None, f"{bold('Отправил место')} #venue"
        elif self.message.contact:
            return None, f"{bold('Отправил контакт')} #contact"
        elif self.message.game:
            return None, f"{bold('Запустил игру')} #game"
        elif self.message.chat_background_set:
            return None, f"{bold('Изменил фон чата')} #chat_background_set"
        else:
            return None, f"{bold('Неизвестное действие')} #unknown #{self.message.content_type}"

    def get_chat_action_description(self) -> Optional[str]:
        """
        Provides a description for chat-specific actions and events.

        This method processes actions such as chat title changes, member additions, and
        forum topic management, returning a descriptive string.

        :return: A description of the chat action, or None if no action is recognized.
        :rtype: Optional[str]
        """
        # Chat modifications (e.g., title changes, photo deletions, member additions)
        if self.message.new_chat_title:
            action = f"{bold('Изменил название чата')} #new_chat_title"
        elif self.message.delete_chat_photo:
            action = f"{bold('Удалил аватар чата')} #delete_chat_photo"
        elif self.message.left_chat_member:
            action = f"{bold('Участник покинул чат')} #left_chat_member"
        elif self.message.connected_website:
            action = f"{bold('Подключил веб-сайт')} #connected_website"
        elif self.message.new_chat_members:
            action = f"{bold('Добавил новых участников в чат')} #new_chat_members"
        elif self.message.write_access_allowed:
            action = f"{bold('Предоставил доступ к записи')} #write_access_allowed"
        elif self.message.message_auto_delete_timer_changed:
            action = f"{bold('Изменил таймер авто-удаления сообщений')} #auto_delete_timer_changed"

        # Chat creation events (e.g., group or channel creation)
        elif self.message.group_chat_created:
            action = f"{bold('Создал группу')} #group_chat_created"
        elif self.message.supergroup_chat_created:
            action = f"{bold('Создал супергруппу')} #supergroup_chat_created"
        elif self.message.channel_chat_created:
            action = f"{bold('Создал канал')} #channel_chat_created"

        # Chat migrations (e.g., upgrades to supergroups)
        elif self.message.migrate_to_chat_id:
            action = (f"{bold('Чат деактивирован:')} #chat_upgrade\n"
                      f"Новый ID: {code(self.message.migrate_to_chat_id)}")
        elif self.message.migrate_from_chat_id:
            action = (f"{bold('Чат стал супергруппой:')} #chat_upgraded\n"
                      f"Старый ID: {code(self.message.migrate_from_chat_id)}")

        # Forum topic actions (e.g., creation, editing, closing)
        elif self.message.forum_topic_created:
            action = f"{bold('Создал тему форума')} #forum_topic_created"
        elif self.message.forum_topic_edited:
            action = f"{bold('Отредактировал тему форума')} #forum_topic_edited"
        elif self.message.forum_topic_closed:
            action = f"{bold('Закрыл тему форума')} #forum_topic_closed"
        elif self.message.forum_topic_reopened:
            action = f"{bold('Открыл тему форума')} #forum_topic_reopened"
        elif self.message.general_forum_topic_hidden:
            action = f"{bold('Скрыл общую тему форума')} #general_forum_topic_hidden"
        elif self.message.general_forum_topic_unhidden:
            action = f"{bold('Открыл общую тему форума')} #general_forum_topic_unhidden"
        elif self.message.proximity_alert_triggered:
            action = f"{bold('Сработал proximity alert')} #proximity_alert_triggered"

        # Video chat events (e.g., scheduling, starting, ending)
        elif self.message.video_chat_scheduled:
            action = f"{bold('Запланировал видеочат')} #video_chat_scheduled"
        elif self.message.video_chat_started:
            action = f"{bold('Начал видеочат')} #video_chat_started"
        elif self.message.video_chat_participants_invited:
            action = f"{bold('Пригласил участников в видеочат')} #video_chat_participants_invited"
        elif self.message.video_chat_ended:
            action = f"{bold('Завершил видеочат')} #video_chat_ended"

        # Payment-related events (e.g., invoices, successful payments)
        elif self.message.invoice:
            action = f"{bold('Отправил счет')} #invoice"
        elif self.message.successful_payment:
            action = f"{bold('Произвел успешный платеж')} #successful_payment"
        elif self.message.refunded_payment:
            action = f"{bold('Возврат платежа')} #refunded_payment"

        # Giveaways
        elif self.message.giveaway:
            action = f"{bold('Создал розыгрыш')} #giveaway"
        elif self.message.giveaway_winners:
            action = f"{bold('Определены победители розыгрыша')} #giveaway_winners"
        elif self.message.giveaway_completed:
            action = f"{bold('Розыгрыш завершён')} #giveaway_completed"

        # Custom user actions (e.g., boosts, shared users)
        elif self.message.boost_added:
            action = f"{bold('Забустил')} #boost_added"
        elif self.message.user_shared:
            action = f"{bold('Поделился пользователем')} #user_shared"
        elif self.message.users_shared:
            action = f"{bold('Поделился пользователями')} #users_shared"
        elif self.message.chat_shared:
            action = f"{bold('Поделился чатом')} #chat_shared"
        elif self.message.passport_data:
            action = f"{bold('Отправил данные паспорта')} #passport_data"
        elif self.message.web_app_data:
            action = f"{bold('Отправил данные веб-приложения')} #web_app_data"
        else:
            action = None
        return action


class TelegramLogHandler:
    """
    Handles logging and interaction with Telegram APIs for logging purposes.

    This class is designed to manage and format logs, handle bot-related updates,
    and forward or process messages and media content within Telegram chats. It also
    includes functionality to retrieve configuration values from the environment
    and update class attributes accordingly.
    """
    _instance = None  # Attribute to store the single class instance

    def __new__(cls, *args, **kwargs):
        """
        Ensures that only one instance of the class is created.

        :return: The single instance of the class.
        :rtype: TelegramLogHandler
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, time_zone_offset: int = 0):
        """
        Initializes the TelegramLogHandler instance.

        :param time_zone_offset: Offset for time zone in hours
        :type time_zone_offset: int
        """
        self.time_zone_offset: int = time_zone_offset
        if not hasattr(self, 'initialized'):  # Ensure initialization runs only once
            self.initialized = True
            self.bot_header: str = 'bot_header'
            self.bot_username: str = 'bot_username'
            self.bot_log_header: str = 'bot_log_header'

            # Fetch environment-specific chat IDs
            self.dev_chat_id: int = int(os.getenv('ID_DEV', 0))
            self.logs_chat_id: int = int(os.getenv('ID_LOGS', 0))
            self.media_chat_id: int = int(os.getenv('ID_MEDIA', 0))
            self.forward_chat_id: int = int(os.getenv('ID_FORWARD', 0))
            self.log_backups_id: int = int(os.getenv('ID_LOG_BACKUPS', 0))

    def update_constants(self):
        """Updates constants from the environment variables if needed"""
        self.dev_chat_id: int = int(os.getenv('ID_DEV', 0))
        self.logs_chat_id: int = int(os.getenv('ID_LOGS', 0))
        self.media_chat_id: int = int(os.getenv('ID_MEDIA', 0))
        self.forward_chat_id: int = int(os.getenv('ID_FORWARD', 0))
        self.log_backups_id: int = int(os.getenv('ID_LOG_BACKUPS', 0))

    @staticmethod
    def channel_link(message: types.Message) -> str:
        """
        Generates a clickable link to a specific channel message.

        :param message: Telegram message instance
        :type message: types.Message

        :return: URL link to the message
        :rtype: str
        """
        link = message.chat.username or re.sub('-100', '', f'c/{message.chat.id}')
        return f'https://t.me/{link}/{message.message_id}'

    async def update_bot_username(self) -> None:
        """Updates the bot's username and related headers if not already set"""
        if self.bot_username == 'bot_username':
            bot_me = await BotInstance().main_bot.get_me()
            self.bot_username = bot_me.username
            self.bot_header = self.get_header(bot_me)
            self.bot_log_header = self.standard_log_heading(bot_me)

    def standard_log_heading(self, user: types.User) -> str:
        """
        Creates a standardized log header.

        :param user: Telegram user or bot instance
        :type user: types.User

        :return: Formatted log header
        :rtype: str
        """
        return f'{self.format_time(tag=code)} {self.get_header(user)}:\n'

    async def send_start_message(self, date: datetime = None) -> None:
        """
        Sends a start message to the developer chat.

        :param date: Optional datetime for the message timestamp
        :type date: datetime, optional
        """
        await self.update_bot_username()
        lines = [f'{self.bot_header}:']
        if date:
            lines.append(self.format_time(date=date, tag=code))
        lines.append(self.format_time(tag=code))
        await main_sender.message(chat_id=self.dev_chat_id, text='\n'.join(lines))

    def get_header(self, chat: Union[types.Chat, types.User], date: datetime = None) -> str:
        """
        Generates a header string for a chat or user.

        :param chat: Chat or User instance
        :type chat: Union[types.Chat, types.User]
        :param date: Optional timestamp for inclusion in the header
        :type date: datetime, optional

        :return: Formatted header string
        :rtype: str
        """
        texts = [self.format_time(date, tag=code)] if date else []
        texts.append(html_secure(chat.full_name))
        texts.append(f'[@{chat.username}]') if chat.username else None
        texts.append(code(chat.id)) if chat.id else None
        return ' '.join(texts)

    def format_time(self, date: datetime = None, tag: code = None, seconds: bool = True) -> str:
        """
        Formats a datetime object into a human-readable string.

        :param date: Datetime object to format (defaults to now if None)
        :type date: datetime, optional.
        :param tag: Optional tag for formatting
        :type tag: code, optional.
        :param seconds: Whether to include seconds in the output
        :type seconds: bool

        :return: Formatted datetime string
        :rtype: str
        """
        date = date or datetime.now(timezone(timedelta(hours=self.time_zone_offset)))
        response = date.strftime(f"{RU_WEEK[date.strftime('%a')]} %d.%m.%Y %H:%M{':%S' if seconds else ''}")
        return tag(response) if tag else response

    async def chat_member(self, message: types.ChatMemberUpdated, log_text: str = None) -> str:
        """
        Handles updates to chat member status and logs them.

        :param message: Information about the chat member update
        :type message: types.ChatMemberUpdated
        :param log_text: Optional additional log text
        :type log_text: str, optional

        :return: Formatted log entry for the chat member update
        :rtype: str
        """
        member_text = ''
        header = f'{self.get_header(message.chat, message.date)}:\n'
        if message.chat.id < 0 and message.from_user:
            header += f'👤 {self.get_header(message.from_user)}:\n'

        new_member = message.new_chat_member.user
        chat_member_logger = ChatMemberLogHandler(message)

        if new_member.id != message.from_user.id:
            permissions = chat_member_logger.compare_permissions()
            action_text, action_hashtag = chat_member_logger.get_action_for_old_member()
            member_text = f"\n{'🤖' if new_member.is_bot else '👤'} {self.get_header(new_member)}"
            if permissions:
                member_text += f'\n{permissions}'
        else:
            action_text, action_hashtag = chat_member_logger.handle_self_action()
        return (
            f"{header}"
            f"{action_text} #{'bot' if new_member.is_bot else 'user'}_{action_hashtag}"
            f"{' #me' if new_member.username == self.bot_username else ''}"
            f"{member_text}{f' {log_text}' if log_text else ''}"
        )

    async def process_media_message(
            self,
            message: types.Message,
            header_parts: list,
    ) -> tuple[list, Optional[str]]:
        """
        Processes media messages for logging.

        :param message: The media message to process
        :type message: types.Message
        :param header_parts: List of header components for the log
        :type header_parts: list

        :return: Updated header parts and caption text, if any
        :rtype: tuple[list, Optional[str]]
        """
        caption_text = EntitiesToHTML(message).convert()
        file_id, description = ProcessMessage(message).get_media_file_id_and_description()
        file_id_line = f'FILE_ID: {code(file_id)}' if file_id else None

        if message.caption and len(message.caption) > 1024:
            file_id = None  # Forward message if caption exceeds limits (premium issue)

        media = await main_sender.message(
            chat_id=self.media_chat_id,
            file_id=file_id,
            text=caption_text,
            from_chat_id=message.chat.id if file_id is None else None,
            forward_id=message.message_id if file_id is None else None,
        )

        if media:
            header_parts.append(self.channel_link(media))

            if isinstance(message.forward_origin, types.MessageOriginChannel):
                forwarded_media_message = types.Message(
                    date=0,
                    chat=message.forward_origin.chat,
                    message_id=message.forward_origin.message_id,
                )
                header_parts.append(self.channel_link(forwarded_media_message))

            if message.sticker:
                header_parts.append(f'https://t.me/addstickers/{message.sticker.set_name}')

            elif message.contact and message.contact.user_id:
                header_parts.append(f'ID пользователя: {code(message.contact.user_id)}')

            header_parts.append(file_id_line) if file_id_line else None
            header_parts.append(f"{description} #media{' с текстом:' if caption_text else ''}")

            header = '\n'.join(
                        [f'{self.bot_header}:'] + header_parts
                    )
            await main_sender.message(chat_id=self.media_chat_id, reply_id=media.message_id, text=blockquote(header))
        return header_parts, caption_text

    async def log_message_handler(
            self,
            message: types.Message,
            from_user: types.User,
            include_details: bool = True
    ) -> tuple[str, Optional[str]]:
        """
        Processes a message and generates log data.

        :param message: Telegram message to handle
        :type message: types.Message
        :param from_user: User who sent the message
        :type from_user: types.User
        :param include_details: Whether to include detailed information in the log
        :type include_details: bool

        :return: Header and body of the log entry
        :rtype: tuple[str, Optional[str]]
        """
        message_body, forwarded_from = None, None
        action_date = message.date if include_details else datetime.now(timezone.utc)
        header_parts = [f'{self.get_header(message.chat, action_date)}:']

        if isinstance(message, types.Message):
            if isinstance(message.forward_origin, types.MessageOriginChat):
                forwarded_from = message.forward_origin.sender_chat
            elif isinstance(message.forward_origin, types.MessageOriginUser):
                forwarded_from = message.forward_origin.sender_user
            elif isinstance(message.forward_origin, types.MessageOriginChannel):
                forwarded_from = message.forward_origin.chat
            elif isinstance(message.forward_origin, types.MessageOriginHiddenUser):
                forwarded_from = types.User(id=0, first_name=message.forward_origin.sender_user_name, is_bot=False)
        else:
            include_details = False
            header_parts.append(f'{message.message_id} #inaccessible')

        if message.chat.id < 0 and from_user:
            header_parts.append(f'👤 {self.get_header(from_user)}:')

        if forwarded_from:
            forwarded_message = await main_sender.message(
                chat_id=self.forward_chat_id,
                forward_id=message.message_id,
                from_chat_id=message.chat.id,
            )

            header_parts.append(
                f"{html_link(self.channel_link(forwarded_message), 'Форвард')}"
                f" от {self.get_header(chat=forwarded_from, date=message.forward_date)}:"
            )

        if include_details:
            if message.pinned_message:
                pinned_header, message_body = await self.log_message_handler(
                    message.pinned_message, message.from_user, include_details=True
                )
                header_parts.extend([
                    f"{bold('Закрепил сообщение:')} #pinned_message",
                    pinned_header,
                ])
            elif message.text:
                message_body = EntitiesToHTML(message).convert()
            else:
                action = ProcessMessage(message).get_chat_action_description()
                if action:
                    header_parts.append(action)
                else:
                    header_parts, message_body = await self.process_media_message(message, header_parts)
        header = '\n'.join(header_parts)
        return header, message_body


class TelegramLogger(TelegramLogHandler):
    async def insert_log_to_queue(self, log_text: str, bot_header: bool = False) -> None:
        """
        Inserts a log entry into the database queue for further processing.

        :param log_text: The text of the log entry to be inserted
        :type log_text: str
        :param bot_header: Whether to include the bot header in the log entry
        :type bot_header: bool
        """
        async with LogRepository() as db:
            if bot_header:
                await self.update_bot_username()
                log_text = f'{self.bot_log_header}{log_text}'
            await db.insert_log(log_text)

    async def log_text_handler(
            self,
            message: Union[types.Message, types.CallbackQuery, types.ChatMemberUpdated],
            log_text: Union[str, bool],
    ) -> None:
        """
        Handles and processes a log entry from a message, callback query, or chat member update.

        :param message: Telegram message, callback query, or chat member update to handle
        :type message: Union[types.Message, types.CallbackQuery, types.ChatMemberUpdated]
        :param log_text: Additional text to include in the log, or a flag to include default text
        :type log_text: Union[str, bool]
        """
        if log_text is not False:
            await self.update_bot_username()
            log_text = '' if log_text in ['', None, True] else log_text
            if isinstance(message, types.CallbackQuery):
                log_header, _ = await self.log_message_handler(
                    message.message, message.from_user, include_details=False
                )
                log_to_queue = blockquote(f"{log_header}\n{log_text or 'Нажал'} #{message.data.upper()}")
            elif isinstance(message, types.ChatMemberUpdated):
                log_to_queue = blockquote(await self.chat_member(message, log_text))
            else:
                log_header, log_body = await self.log_message_handler(message, message.from_user, include_details=True)
                log_to_queue = blockquote(f'{log_header}\n{log_text}' if log_text else log_header)
                log_to_queue += f'\n{log_body}' if log_body else ''

            await self.insert_log_to_queue(log_to_queue)

    async def send_large_log(self, log_chunk: str, log_ids: list[int]) -> None:
        """
        Sends a large log entry by splitting it into smaller chunks.

        :param log_chunk: The large log entry text
        :type log_chunk: str
        :param log_ids: List of log entry IDs to associate with the chunks
        :type log_ids: list[int]
        """
        split_log = log_chunk.split('</blockquote>\n')
        header = split_log.pop(0)
        message = await self.send_message_to_log_channel('</blockquote>'.join(split_log), log_ids=log_ids)
        await self.send_message_to_log_channel(
            f"{header}</blockquote>\n"
            f"{bold('Большое сообщение')}: #split",
            log_ids=log_ids,
            reply_id=message.message_id if message else None,
        )

    async def send_message_to_log_channel(
            self,
            log_text: str,
            log_ids: list[int],
            reply_id: int = None,
    ) -> types.Message:
        """
        Sends a log entry to the log channel and updates the database with the post information.

        :param log_text: The text of the log entry
        :type log_text: str
        :param log_ids: List of IDs for the log entries being sent
        :type log_ids: list[int]
        :param reply_id: ID of the message to reply to, if any
        :type reply_id: int, optional

        :return: The message object for sent log entry
        :rtype: types.Message
        """
        logged_message = await log_sender.message(self.logs_chat_id, text=log_text, reply_id=reply_id)

        async with LogRepository() as db:
            if logged_message:
                await db.update_posted_logs(
                    record_ids=log_ids,
                    post_date=logged_message.date,
                    post_id=logged_message.message_id,
                )

        # Check if logs need to be saved as backups
        if logged_message and logged_message.message_id % LOGS_CUTOFF == 0:
            async with LogRepository() as db:
                posted_logs = await db.get_posted_logs()

            if posted_logs:
                log_ids_to_delete = []
                backup = {
                    'bot_username': self.bot_username,
                    'start_date': posted_logs[0].post_date,
                    'end_date': posted_logs[-1].post_date,
                    'data': [],
                }
                for log in posted_logs:
                    backup['data'].append(log.text)
                    log_ids_to_delete.append(log.id)

                file_name = (
                    f'logs_{self.bot_username.lower()}'
                    f'_from_{logged_message.message_id - len(posted_logs)}'
                    f'_to_{logged_message.message_id}.json'
                )
                file = types.BufferedInputFile(json.dumps(backup).encode('utf-16'), filename=file_name)
                response = await log_sender.message(self.log_backups_id, file=file, text=self.bot_log_header)

                async with LogRepository() as db:
                    await db.remove_posted_logs(log_ids_to_delete)

                dev_text = (
                    f"{bold(f'Сохранены логи бота @{self.bot_username}:')}\n"
                    f"{self.channel_link(response)}"
                )
                await log_sender.message(self.dev_chat_id, text=dev_text)
        return logged_message

    async def send_logs_to_telegram(self) -> None:
        """
        Retrieves pending logs from the database and sends them to the log channel in Telegram.
        Splits large logs into smaller chunks if necessary.
        """
        async with LogRepository() as db:
            log_entries = await db.get_logs_to_post()
        if log_entries:
            current_log_ids = []
            current_log_chunk = ''
            logs_to_send = defaultdict(list)
            for log in log_entries:
                if len(sub_tag(f'{current_log_chunk}{log.text}')) <= 4096:
                    current_log_ids.append(log.id)
                    current_log_chunk += f'{log.text}\n'
                else:
                    logs_to_send[current_log_chunk.strip('\n')].extend(current_log_ids)
                    current_log_ids = [log.id]
                    current_log_chunk = f'{log.text}\n'

            if current_log_chunk:
                logs_to_send[current_log_chunk.strip('\n')].extend(current_log_ids)

            for log_chunk, log_ids in logs_to_send.items():
                if len(log_chunk) > 4096:
                    await self.send_large_log(log_chunk, log_ids)
                else:
                    await self.send_message_to_log_channel(log_chunk, log_ids)

                await asyncio.sleep(15)
        await asyncio.sleep(1)

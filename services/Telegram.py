import re
import asyncio
import filetype
from typing import Optional
from aiogram import types, Bot
from functions.html import html_secure
from services.bot_instance import BotInstance


class MessageSender:
    """
    A class responsible for sending and editing messages in a Telegram chat.

    It provides methods to send text messages, media (photos, videos, documents, etc.), and to edit or forward messages.
    The class handles different types of content and message customization, such as adding keyboards, link previews,
    and handling retries for temporary errors.
    """
    def __init__(self, use_main_bot: bool = True, link_preview: bool = True):
        """
        Initializes the MessageSender class.

        :param use_main_bot: Whether to use the main bot instance for sending messages. Defaults to True.
        :type use_main_bot: bool
        :param link_preview: Whether to enable link previews for links in messages. Defaults to True.
        :type link_preview: bool
        """
        self.use_main_bot = use_main_bot
        self.override_link_preview: bool = link_preview

    @property
    def bot(self) -> Bot:
        """Returns the bot instance based on the configuration"""
        if self.use_main_bot:
            return BotInstance().main_bot
        else:
            return BotInstance().log_bot

    async def answer(self, call_id: str, text: str = None, alert: bool = False) -> None:
        """
        Wrapper for answering a callback query.

        :param call_id: The callback query identifier.
        :type call_id: str
        :param text: The text to display in the callback query answer.
        :type text: str, optional
        :param alert: Whether to show an alert (popup) for the callback query.
        :type alert: bool, optional
        """
        try:
            await self.bot.answer_callback_query(call_id, text, show_alert=alert)
        except IndexError and Exception:
            pass

    @staticmethod
    def process_files(
            file_id: Optional[str] = None,
            file: Optional[str | types.BufferedInputFile] = None,
            files: Optional[list[str | types.BufferedInputFile]] = None,
    ) -> tuple[Optional[str], Optional[types.BufferedInputFile], list[types.BufferedInputFile]]:
        """
        Processes the input parameters file_id, file, and files, returning them in a consistent format:
        - file_id: file identifier in string format (if file is a string)
        - file: instance of types.BufferedInputFile (if file or files contain types.BufferedInputFile)
        - files: list of types.BufferedInputFile objects (if multiple files are provided).

        :param file_id: The file ID to be processed.
        :type file_id: Optional[str]
        :param file: The file object to be processed.
        :type file: Optional[str | types.BufferedInputFile]
        :param files: List of files to be processed.
        :type files: Optional[list[str | types.BufferedInputFile]]
        :return: A tuple containing file_id, file, and files in the consistent format.
        :rtype: tuple[Optional[str], Optional[types.BufferedInputFile], list[types.BufferedInputFile]]
        """

        # Initialize files as an empty list if not provided
        files = files or []

        # If file_id is provided, add it to the beginning of the files list
        if file_id:
            files.insert(0, file_id)
            file_id = None

        # If file is provided, add it to the beginning of the files list
        if file:
            files.insert(0, file)
            file = None

        # If files contains only one item, process it
        if len(files) == 1:
            single_file = files[0]
            # If it's a string, treat it as a file_id
            if isinstance(single_file, str):
                file = None
                file_id = single_file
            else:
                file_id = None
                file = single_file  # It's a types.BufferedInputFile
            files = []

        return file_id, file, files

    async def message(
            self, chat_id: int | str,
            text: str = None,
            keyboard: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup = None,
            edit_message: int | str | types.Message = None,
            file_id: str = None,
            file: str | types.BufferedInputFile = None,
            files: list[str | types.BufferedInputFile] = None,
            dice: str = None,
            link_preview: bool = None,
            reply_id: int = None,
            pin_id: int = None,
            from_chat_id: int = None,
            forward_id: int = None,
            copy_id: int = None,
            thread_id: int = None,
            protect: bool = False,
            raises: bool = True,
            attempt: int = 0,
    ) -> types.Message:
        """
        Sends or edits a message in a Telegram chat.

        :param chat_id: The ID of the Telegram chat where the message will be sent.
        :type chat_id: int | str

        :param text: The text of the message to be sent.
        :type text: str, optional

        :param keyboard: A keyboard markup, either InlineKeyboardMarkup or ReplyKeyboardMarkup.
        :type keyboard: optional

        :param edit_message: Specifies a message to edit instead of sending a new one (only for text messages).
        :type edit_message: int | str | types.Message, optional

        :param file_id: ID of a file to send
            (can be a document, animation, photo, video, video note, audio, voice or sticker).
        :type file_id: str, optional

        :param file: File object to send.
            This can be used to upload a file directly from the local system.
            It should be an instance of `types.BufferedInputFile`.
        :type file: str | types.BufferedInputFile, optional

        :param files: List of file IDs or file objects to send.
            Each item in the list can either be a file ID (str) or an `InputFile` object.
            This is useful for sending multiple files in one media group.
        :type files: list[str | types.BufferedInputFile], optional

        :param dice: Type of dice emoji to send. Accepted values are '🎲', '🎯', '🏀', '⚽️', '🎳', or '🎰'.
        :type dice: str, optional

        :param link_preview: Controls whether to enable a web page preview for links. Defaults to True.
        :type link_preview: bool, optional

        :param reply_id: ID of the message to reply to.
        :type reply_id: int, optional

        :param pin_id: ID of the message to pin in the chat.
        :type pin_id: int, optional

        :param from_chat_id: The ID of the original chat from which the message is forwarded or copied.
        :type from_chat_id: int, optional

        :param forward_id: ID of the message to forward from `from_chat_id` to `chat_id`.
        :type forward_id: int, optional

        :param copy_id: ID of the message to copy from `from_chat_id` to `chat_id`.
        :type copy_id: int, optional

        :param thread_id: ID of the message thread in which the message will be sent.
        :type thread_id: int, optional

        :param protect: If set to True, protects the message contents from being forwarded.
        :type protect: bool, optional

        :param raises: If set to True, the function will raise errors when they occur.
            If set to False, errors will be ignored without raising exceptions.
        :type raises: bool, optional

        :param attempt: Attempt counter for minor errors
        :param attempt: int

        :return: Sent or edited message, on success.
        :rtype: types.Message
        """

        response = None
        chat_id = int(chat_id)
        file_id, file, files = self.process_files(file_id, file, files)

        # If the edit_message is inaccessible, set it to None
        if isinstance(edit_message, types.InaccessibleMessage):
            edit_message = None

        # If link_preview is not provided, using the instance default (self.override_link_preview)
        # Otherwise, respect the provided link_preview argument.
        disable_link_preview = not (link_preview if link_preview is not None else self.override_link_preview)

        try:
            if dice:
                response = await self.bot.send_dice(
                    chat_id=chat_id, emoji=dice, reply_markup=keyboard,
                    reply_to_message_id=reply_id, message_thread_id=thread_id, protect_content=protect
                )

            elif forward_id and from_chat_id:
                response = await self.bot.forward_message(
                    chat_id=chat_id, from_chat_id=from_chat_id,
                    message_id=forward_id, message_thread_id=thread_id, protect_content=protect
                )

            elif copy_id and from_chat_id:
                response = await self.bot.copy_message(
                    chat_id=chat_id, from_chat_id=from_chat_id, message_id=copy_id,
                    reply_to_message_id=reply_id, message_thread_id=thread_id, protect_content=protect
                )

            elif file_id:
                kwargs = {
                    'caption': text,
                    'chat_id': chat_id,
                    'parse_mode': 'HTML',
                    'reply_markup': keyboard,
                    'protect_content': protect,
                    'message_thread_id': thread_id,
                    'reply_to_message_id': reply_id,
                }

                if file_id.startswith('BAA'):
                    response = await self.bot.send_video(video=file_id, **kwargs)
                elif file_id.startswith('BQA'):
                    response = await self.bot.send_document(document=file_id, **kwargs)
                elif file_id.startswith('AgA'):
                    response = await self.bot.send_photo(photo=file_id, **kwargs)
                elif file_id.startswith('CAA'):
                    del kwargs['caption'], kwargs['parse_mode']
                    response = await self.bot.send_sticker(sticker=file_id, **kwargs)
                elif file_id.startswith('DQA'):
                    del kwargs['caption'], kwargs['parse_mode']
                    response = await self.bot.send_video_note(video_note=file_id, **kwargs)
                elif file_id.startswith('CQA'):
                    response = await self.bot.send_audio(audio=file_id, **kwargs)
                elif file_id.startswith('AwA'):
                    response = await self.bot.send_voice(voice=file_id, **kwargs)
                elif file_id.startswith('CgA'):
                    response = await self.bot.send_animation(animation=file_id, **kwargs)

            elif file:
                kwargs = {
                    'caption': text,
                    'chat_id': chat_id,
                    'parse_mode': 'HTML',
                    'reply_markup': keyboard,
                    'protect_content': protect,
                    'message_thread_id': thread_id,
                    'reply_to_message_id': reply_id,
                }
                file_type = filetype.guess(file.data)
                if file_type is None:  # If the file is unrecognized
                    response = await self.bot.send_document(document=file, **kwargs)
                elif file_type.mime.startswith('video'):
                    # Attempt to send video as an animation, fallback to video if not possible
                    response = await self.bot.send_animation(animation=file, **kwargs)
                elif file_type.mime.startswith('image'):
                    response = await self.bot.send_photo(photo=file, **kwargs)
                elif file_type.mime.startswith('audio'):
                    response = await self.bot.send_audio(audio=file, **kwargs)
                else:
                    response = await self.bot.send_document(document=file, **kwargs)

            elif files:
                media = []
                for file_value in files:
                    caption = text if len(media) == 0 else None
                    if isinstance(file_value, str):
                        file_value: str
                        input_media = {
                            'BAA': types.InputMediaVideo,  # video
                            'AgA': types.InputMediaPhoto,  # photo
                            'CQA': types.InputMediaAudio,  # audio
                            'BQA': types.InputMediaDocument,  # document
                        }.get(file_value[:3])

                        if input_media:  # Bot can't send media group with other message types
                            media.append(input_media(media=file_value, caption=caption, parse_mode='HTML'))
                        else:
                            raise ValueError("Can't handle this file_id in media group")
                    else:
                        file_value: types.BufferedInputFile
                        file_type = filetype.guess(file_value.data)
                        if file_type is None:  # If the file is unrecognized
                            input_media = types.InputMediaDocument
                        elif file_type.mime.startswith('video'):
                            input_media = types.InputMediaVideo
                        elif file_type.mime.startswith('image'):
                            input_media = types.InputMediaPhoto
                        elif file_type.startswith('audio'):
                            input_media = types.InputMediaAudio
                        else:
                            input_media = types.InputMediaDocument
                        media.append(input_media(media=file_value, caption=caption, parse_mode='HTML'))
                if media:
                    response = await self.bot.send_media_group(
                        chat_id=chat_id, media=media[:10],
                        reply_to_message_id=reply_id, message_thread_id=thread_id, protect_content=protect)

            elif pin_id:
                response = await self.bot.pin_chat_message(chat_id=chat_id, message_id=pin_id)

            elif edit_message:
                if type(edit_message) in [str, int]:
                    message_id = int(edit_message)
                    response = await self.bot.edit_message_text(
                        text=text, chat_id=chat_id, message_id=message_id,
                        reply_markup=keyboard, disable_web_page_preview=disable_link_preview, parse_mode='HTML')
                else:
                    entities = edit_message.entities if text is None else None
                    chat_id, message_id = edit_message.chat.id, edit_message.message_id
                    keyboard = edit_message.reply_markup if keyboard is True else keyboard
                    modified_text = html_secure(re.sub('<.*?>', '', text), reverse=True).strip() if text else None

                    if edit_message.text == modified_text or text is None:
                        if keyboard != edit_message.reply_markup:
                            response = await self.bot.edit_message_reply_markup(
                                chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
                        else:
                            response = edit_message
                    else:
                        if edit_message.caption is not None:
                            response = await self.bot.edit_message_caption(
                                chat_id=chat_id, message_id=message_id,
                                caption=text, reply_markup=keyboard, parse_mode='HTML')
                        else:
                            await self.bot.edit_message_text(
                                text=text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard,
                                entities=entities, disable_web_page_preview=disable_link_preview, parse_mode='HTML')
            elif text:
                response = await self.bot.send_message(
                    chat_id=chat_id, text=text,
                    reply_markup=keyboard, reply_to_message_id=reply_id, message_thread_id=thread_id,
                    disable_web_page_preview=disable_link_preview, protect_content=protect, parse_mode='HTML')
        except IndexError and Exception as error:
            search_retry = re.search(
                r'(Too Many Requests: retry after|Retry in|Please try again in) (\d+)(\n| seconds)*',
                string=str(error),
            )
            if (
                search_retry
                or re.search('Temporary failure in name resolution', str(error))
                or re.search('Cannot connect to host api.telegram.org', str(error))
                or re.search('Connection to api.telegram.org timed out', str(error))
                or re.search('Error code: 502. Description: Bad Gateway', str(error))
            ):
                if search_retry:
                    await asyncio.sleep(int(search_retry.group(2)) + 1)
                else:
                    attempt += 1
                    await asyncio.sleep(0.1 * (attempt ** (attempt - 1)))

                response = await self.message(
                    chat_id, text, keyboard, edit_message, file_id, file, files, dice, link_preview,
                    reply_id, pin_id, from_chat_id, forward_id, copy_id, thread_id, protect, raises, attempt,
                )
            elif re.search('(Query is too old|exactly the same)', str(error)):
                pass
            elif raises:
                raise error
        return response

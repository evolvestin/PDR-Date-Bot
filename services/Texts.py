import re
import json
from functions.html import bold
from database.models import Texts
from collections import defaultdict
from gspread_asyncio import AsyncioGspreadSpreadsheet
from database.texts_repository import TextsRepository


class TextsService:
    """
    Service class for handling text-related operations, such as retrieving language codes,
    emojis for categories, and formatting time left for lots.

    This class provides methods to interact with the texts repository and format
    time-related information in a human-readable format.
    """

    @staticmethod
    def time_left_text(
            texts: dict[str, str],
            seconds: int,
            shortened: bool,
            show_years: bool,
            show_weeks: bool,
            show_days: bool,
            show_hours: bool,
            show_minutes: bool,
            show_seconds: bool,
    ) -> str:
        """
        Converts a given time in seconds to a human-readable format based on the provided options.

        :param texts: Dictionary containing the translations for the time units.
        :type texts: dict[str, str]
        :param seconds: The time left in seconds.
        :type seconds: int
        :param shortened: Whether to use shortened unit names.
        :type shortened: bool
        :param show_years: Whether to display years in the result.
        :type show_years: bool
        :param show_weeks: Whether to display weeks in the result.
        :type show_weeks: bool
        :param show_days: Whether to display days in the result.
        :type show_days: bool
        :param show_hours: Whether to display hours in the result.
        :type show_hours: bool
        :param show_minutes: Whether to display minutes in the result.
        :type show_minutes: bool
        :param show_seconds: Whether to display seconds in the result.
        :type show_seconds: bool

        :return: A string representing the time left in a human-readable format.
        :rtype: str
        """
        units = []
        data = {
            'year': 365 * 24 * 60 * 60 if show_years else 0,
            'week': 7 * 24 * 60 * 60 if show_weeks else 0,
            'day': 24 * 60 * 60 if show_days else 0,
            'hour': 60 * 60 if show_hours else 0,
            'minute': 60 if show_minutes else 0,
            'second': 1 if show_seconds else 0,
        }
        for key, value in data.items():
            count = int(seconds / value) if value > 0 else 0
            if count > 0:
                if shortened:
                    units.append(f"{count}{' ' if key == 'minute' else ''}{texts[f'unit_{key}']}")
                else:
                    if count % 100 in [11, 12, 13, 14] or (texts['id'] == 'en' and count >= 2):
                        unit_text = texts[f'unit_{key}_3']
                    else:
                        unit_text = texts[f'unit_{key}_1'] if count % 10 == 1 else texts[f'unit_{key}_3']
                        unit_text = texts[f'unit_{key}_2'] if count % 10 in [2, 3, 4] else unit_text
                    units.append(f'{count} {unit_text}')
            seconds -= count * value
        return (' ' if shortened else ', ').join(units)
    # unit_year_1, unit_year_2, unit_year_3, unit_week_1, unit_week_2, unit_week_3,
    # unit_day_1, unit_day_2, unit_day_3, unit_hour_1, unit_hour_2, unit_hour_3,
    # unit_minute_1, unit_minute_2, unit_minute_3, unit_second_1, unit_second_2, unit_second_3

    def period_week_and_day(self, texts: dict[str, str], difference_seconds: int) -> str:
        text = self.time_left_text(
            texts=texts,
            seconds=difference_seconds,
            shortened=False,
            show_years=False,
            show_weeks=True,
            show_days=True,
            show_hours=False,
            show_minutes=False,
            show_seconds=False,
        )
        return re.sub(', ', f" {texts['unit_separator']} ", text)


class TextsUpdater(TextsService):
    """
    A subclass of TextsService responsible for updating and syncing text data with the local database.

    This class is used to fetch text data from a spreadsheet, update the local database, and
    ensure the text content is synchronized across the system. It also manages the maximum
    lengths of unit texts for formatting purposes.
    """

    @staticmethod
    async def check_texts_exist_in_database() -> bool:
        """
        Checks if there are any texts in the database.

        :return: True if there are texts, False otherwise.
        :rtype: bool
        """
        async with TextsRepository() as db:
            text = await db.get_any_texts()
        return True if text else False

    async def update_texts_in_local_database(self, spreadsheet: AsyncioGspreadSpreadsheet) -> str:
        """
        Updates the texts in the local database by synchronizing them with the provided spreadsheet.

        :param spreadsheet: The spreadsheet containing the updated texts.
        :type spreadsheet: AsyncioGspreadSpreadsheet

        :return: A summary of the added and updated texts.
        :rtype: str
        """
        lines = []
        worksheet = await spreadsheet.worksheet(title='texts')
        data = await worksheet.get('A1:Z50000', major_dimension='ROWS')

        texts, max_length_unit_texts = self.generate_texts(data)

        async with TextsRepository() as db:
            added_ids, updated_ids = await db.sync_texts(texts)

        for head, ids_dict in [('Добавлены', added_ids), ('Обновлены', updated_ids)]:
            for language_code, values_list in ids_dict.items():
                lines.append(f"{head} значения {bold(language_code.upper())} с id: {', '.join(values_list)}")

        return '\n'.join(lines) or '❌ Ничего не обновлено.'

    @staticmethod
    def generate_texts(data: list[list[str]]) -> tuple[list[Texts], dict[str, str]]:
        """
        Generates a list of Texts objects and a dictionary of maximum unit lengths from the given data.

        :param data: The raw data from the spreadsheet.
        :type data: list[list[str]]

        :return: A tuple containing the list of Texts objects and a dictionary of unit max lengths.
        :rtype: tuple[list[Texts], dict[str, str]]
        """
        response = []
        unit_max_lengths = defaultdict(str)
        linked_commands_by_lang = defaultdict(list[dict])
        language_codes = list(map(str.strip, data[0])) if len(data) > 0 else []
        language_codes.pop(0) if language_codes else None  # Remove the first element that corresponds to the text IDs

        for row in data:
            text_id = row.pop(0).strip() if len(row) > 1 else None
            if text_id:
                for language_code, content in zip(language_codes, row):
                    if text_id in ['ended', 'subscribe', 'unit_day', 'unit_hour', 'unit_minute', 'unit_second']:
                        if len(content.strip()) > len(unit_max_lengths[text_id]):
                            unit_max_lengths[text_id] = content.strip()
                    if text_id and text_id.startswith('command_'):
                        linked_commands_by_lang[language_code].append(
                            {
                                'command': re.sub('command_', '', text_id),
                                'description': content,
                            }
                        )
                    response.append(
                        Texts(
                            text_id=text_id,
                            language=language_code,
                            content=content.strip(),
                        )
                    )

        # JSON template for user-defined command descriptions, order is defined in the Google Sheets table
        for language_code, commands in linked_commands_by_lang.items():
            response.append(
                Texts(
                    text_id='BOT_COMMANDS',
                    language=language_code,
                    content=json.dumps(commands),
                )
            )
        return response, dict(unit_max_lengths)

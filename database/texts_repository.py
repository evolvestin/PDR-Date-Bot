from database.models import Texts
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from database.session import init_sqlite_session
from sqlalchemy import delete, func, literal, select


class TextsRepository:
    """A repository for managing text records in the database"""
    async def __aenter__(self) -> 'TextsRepository':
        """Creates a session and connects to the database, returns a repository instance"""
        self.connection: AsyncSession = init_sqlite_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes the session when exiting the context, releasing database connection resources"""
        if self.connection:
            await self.connection.close()
    
    async def get_texts(self) -> list[Texts]:
        """
        Retrieves all saved texts from the database.

        :return: List of all text records in the database.
        :rtype: list[Texts]
        """
        result = await self.connection.execute(
            select(Texts)
            .order_by(Texts.id)
        )
        return list(result.scalars().all())

    async def get_any_texts(self) -> Texts:
        """
        Retrieve one or zero texts from the database.

        :return: A Texts record.
        :rtype: Texts
        """
        result = await self.connection.execute(
            select(Texts)
        )
        return result.scalars().first()

    async def get_all_language_codes(self) -> list[str]:
        """
        Retrieves all unique language codes from the database.

        :return: List of language codes (e.g., 'ru', 'en', 'es').
        :rtype: list[str]
        """
        result = await self.connection.execute(
            select(Texts.language, func.min(Texts.id))
            .group_by(Texts.language)
            .order_by(func.min(Texts.id))
        )
        return list(result.scalars().all())

    async def get_texts_by_language(self, language: str) -> dict[str, str]:
        """
        Retrieves all texts for a specified language.

        :param language: The language code to filter texts by (e.g., 'en', 'ru').
        :type language: str

        :return: Dictionary of text IDs mapped to their content.
        :rtype: dict[str, str]
        """
        response = {}
        result = await self.connection.execute(
            select(Texts)
            .where(Texts.language == literal(language))
        )
        for record in result.scalars().all():
            response.update({record.text_id: record.content})
        return response
    
    async def sync_texts(self, texts: list[Texts]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """
        Synchronizes the database texts with the provided list, updating or deleting as necessary.

        :param texts: List of text records to synchronize with the database.
        :type texts: list[Texts]

        :return: Two dictionaries:
            - Added IDs grouped by language.
            - Updated IDs grouped by language.
        :rtype: tuple[dict[str, list[str]], dict[str, list[str]]]
        """
        existing_texts = await self.get_texts()  # Get all existing records
        added_ids, updated_ids = defaultdict(list), defaultdict(list)
        texts_to_add, existing_text_keys, text_keys_to_delete = [], [], []
        new_text_keys_dict = {(text.text_id, text.language): text for text in texts}

        for text in existing_texts:
            text_key = (text.text_id, text.language)
            if text_key in new_text_keys_dict:
                existing_text_keys.append(text_key)
                if text.content != new_text_keys_dict[text_key].content:
                    updated_ids[text.language].append(text.text_id)
                text.content = new_text_keys_dict[text_key].content
            else:
                updated_ids[text.language].append(text.text_id)
                text_keys_to_delete.append(text_key)

        for text_key, text in new_text_keys_dict.items():
            if text_key not in existing_text_keys:
                texts_to_add.append(text)
                added_ids[text.language].append(text.text_id)

        if texts_to_add:
            self.connection.add_all(texts_to_add)

        if text_keys_to_delete:
            for text_id, text_language in text_keys_to_delete:
                await self.connection.execute(
                    delete(Texts)
                    .where(Texts.text_id == literal(text_id), Texts.language == literal(text_language))
                )
        await self.connection.commit()
        return dict(added_ids), dict(updated_ids)

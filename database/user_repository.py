from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, func, select
from database.models import User, UserPregnancy
from sqlalchemy.ext.asyncio import AsyncSession
from database.session import init_postgres_session


class UserRepository:
    """
    Handles database operations related to User entities.

    Provides methods to fetch, create, update, and synchronize user data
    from and to the database, ensuring efficient interactions with User records.
    """
    async def __aenter__(self) -> 'UserRepository':
        """Creates a session and connects to the database, returns a repository instance"""
        self.connection: AsyncSession = init_postgres_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes the session when exiting the context, releasing database connection resources"""
        if self.connection:
            await self.connection.close()

    async def get_user_by_telegram_id(self, telegram_id: int) -> User:
        """
        Retrieve a user by their Telegram ID.

        :param telegram_id: The Telegram ID of the user.
        :type telegram_id: int
        :return: The user instance matching the Telegram ID or None if not found.
        :rtype: User
        """
        result = await self.connection.execute(
            select(User)
            .where(User.id == telegram_id)
        )
        return result.scalars().first()

    async def get_users_to_backup(self) -> list[User]:
        """
        Retrieve all users that require a backup update.

        :return: A list of users marked for backup.
        :rtype: list[User]
        """
        result = await self.connection.execute(
            select(User)
            .where(User.needs_backup_update.is_(True))
        )
        return list(result.scalars().all())

    async def get_any_user(self) -> User:
        """
        Retrieve one or zero user from the database.

        :return: A User record.
        :rtype: User
        """
        result = await self.connection.execute(
            select(User)
        )
        return result.scalars().first()

    async def get_all_users(self) -> list[User]:
        """
        Retrieve all users from the database.

        :return: A list of all user records.
        :rtype: list[User]
        """
        result = await self.connection.execute(
            select(User)
        )
        return list(result.scalars().all())

    async def update_user_username_and_reaction(self, user: User, username: str, reaction: bool) -> None:
        """
        Update a user's username and reaction status in the database.
        Marks the user for backup after the update.

        :param user: The user object to be updated.
        :type user: User
        :param username: The new username to be set.
        :type username: str
        :param reaction: The new reaction status.
        :type reaction: bool
        """
        user.username = username
        user.reaction = reaction
        user.needs_backup_update = True
        self.connection.add(user)
        await self.connection.commit()

    async def create_user(self, new_user: User, reaction: bool) -> User:
        """
        Create a new user in the database.
        Automatically assigns a unique `google_row_id` and marks the user for backup.

        :param new_user: The new user object to be created.
        :type new_user: User
        :param reaction: The new user reaction.
        :type reaction: User
        :return: The created user with updated attributes.
        :rtype: User
        """
        result = await self.connection.execute(
            select(func.max(User.google_row_id))
        )
        max_id = result.scalar() or 1
        new_user.reaction = reaction
        new_user.google_row_id = max_id + 1
        new_user.needs_backup_update = True

        self.connection.add(new_user)
        await self.connection.commit()
        return new_user

    async def update_user_personal_data(self, user: User, full_name: str, username: str) -> None:
        """
        Update a user's personal data, including full name and username. Marks the user for backup after the update.

        :param user: The user object to be updated.
        :type user: User
        :param full_name: The new full name to be set.
        :type full_name: str
        :param username: The new username to be set.
        :type username: str
        """
        user.full_name = full_name
        user.username = username
        user.needs_backup_update = True
        self.connection.add(user)
        await self.connection.commit()

    async def update_user_reaction(self, user: User, reaction: bool) -> None:
        """
        Update a user's reaction status and optionally set a block date.
        Marks the user for backup after the update.

        :param user: The user object to be updated.
        :type user: User
        :param reaction: The new reaction status.
        :type reaction: bool
        """
        user.reaction = reaction
        user.needs_backup_update = True
        self.connection.add(user)
        await self.connection.commit()

    async def update_user_language(self, user: User, language: str) -> None:
        """
        Update a user's preferred language. Marks the user for backup after the update.

        :param user: The user object to be updated.
        :type user: User
        :param language: The new language preference.
        :type language: str
        """
        user.language = language
        user.needs_backup_update = True
        self.connection.add(user)
        await self.connection.commit()

    async def mark_user_as_synced(self, user: User) -> None:
        """
        Mark a user as synchronized with Google Sheets.

        :param user: The user object to be marked as synced.
        :type user: User
        """
        user.needs_backup_update = False
        self.connection.add(user)
        await self.connection.commit()

    async def sync_users(self, users: list[User]) -> None:
        """
        Synchronize a list of users with the database.
        Updates existing records and adds new users if not already present.

        :param users: A list of users to synchronize.
        :type users: list[User]
        """
        users_to_add, existing_user_ids = [], []
        existing_users = await self.get_all_users()  # Get all existing records
        new_users_dict = {user.id: user for user in users}

        for user in existing_users:
            if user.id in new_users_dict:
                existing_user_ids.append(user.id)
                user.full_name = new_users_dict[user.id].full_name
                user.username = new_users_dict[user.id].username
                user.language = new_users_dict[user.id].language
                user.reaction = new_users_dict[user.id].reaction
                user.google_row_id = new_users_dict[user.id].google_row_id

        for user_id, user in new_users_dict.items():
            if user_id not in existing_user_ids:
                users_to_add.append(user)

        if users_to_add:
            self.connection.add_all(users_to_add)

        await self.connection.commit()


class UserPregnancyRepository:
    """Repository class for handling operations with user pregnancy in the database"""
    async def __aenter__(self) -> 'UserPregnancyRepository':
        """Creates a session and connects to the database, returns a repository instance"""
        self.connection: AsyncSession = init_postgres_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Closes the session when exiting the context, releasing database connection resources"""
        if self.connection:
            await self.connection.close()

    async def get_all_pregnancy(self) -> list[UserPregnancy]:
        """
        Retrieves all user pregnancy records from the database.

        :return: A list of all user pregnancy.
        :rtype: list[UserPregnancy]
        """
        result = await self.connection.execute(
            select(UserPregnancy)
        )
        return list(result.scalars().all())

    async def get_user_period_pregnancy(self) -> list[tuple[User, UserPregnancy]]:
        result = await self.connection.execute(
            select(User, UserPregnancy)
            .join(User, and_(UserPregnancy.user_id == User.id))
            .where(UserPregnancy.period_date.isnot(None))
            .options(joinedload(UserPregnancy.user))
        )
        return list((row[0], row[1]) for row in result.all())

    async def get_users_with_today_pdr(self, now: datetime) -> list[tuple[User, UserPregnancy]]:
        date = datetime.fromisoformat(now.strftime(f'%Y-%m-%d 00:00:00'))
        result = await self.connection.execute(
            select(User, UserPregnancy)
            .join(User, and_(UserPregnancy.user_id == User.id))
            .where(UserPregnancy.pdr_date == date)
            .options(joinedload(UserPregnancy.user))
        )
        return list((row[0], row[1]) for row in result.all())

    async def get_or_create_user_pregnancy(self, user_id: int, chat_id: int) -> UserPregnancy | None:
        result = await self.connection.execute(
            select(UserPregnancy)
            .where(
                UserPregnancy.user_id == user_id,
                UserPregnancy.chat_id == chat_id,
            )
        )
        response = result.scalars().first()
        if not response:
            result = await self.connection.execute(
                select(func.max(UserPregnancy.id))
            )
            max_id = result.scalar() or 1
            response = UserPregnancy(
                id=max_id + 1,
                user_id=user_id,
                chat_id=chat_id,
                gender=None,
                pdr_date=None,
                period_date=None,
                needs_backup_update=True,
            )
            self.connection.add(response)
            await self.connection.commit()
        return response

    async def get_pregnancies_to_backup(self) -> list[UserPregnancy]:
        """
        Retrieves all user pregnancies marked for backup.

        :return: A list of pregnancies that need backup updates.
        :rtype: list[UserPregnancy]
        """
        result = await self.connection.execute(
            select(UserPregnancy)
            .where(UserPregnancy.needs_backup_update.is_(True))
        )
        return list(result.scalars().all())

    async def update_user_period_date(self, pregnancy: UserPregnancy, period_date: datetime) -> None:
        pregnancy.period_date = period_date
        pregnancy.needs_backup_update = True
        self.connection.add(pregnancy)
        await self.connection.commit()

    async def update_user_pdr_date(self, pregnancy: UserPregnancy, pdr_date: datetime) -> None:
        pregnancy.pdr_date = pdr_date
        pregnancy.needs_backup_update = True
        self.connection.add(pregnancy)
        await self.connection.commit()

    async def update_user_baby_gender(self, pregnancy: UserPregnancy, gender_id: int) -> None:
        pregnancy.gender = gender_id
        pregnancy.needs_backup_update = True
        self.connection.add(pregnancy)
        await self.connection.commit()

    async def mark_pregnancy_as_synced(self, pregnancy: UserPregnancy) -> None:
        """
        Marks a user date as synced (backup updated).

        :param pregnancy: The date to mark as synced.
        :type pregnancy: UserPregnancy
        """
        pregnancy.needs_backup_update = False
        self.connection.add(pregnancy)
        await self.connection.commit()

    async def sync_pregnancies(self, pregnancies: list[UserPregnancy]) -> None:
        """
        Synchronizes user pregnancies with the database.

        :param pregnancies: A list of pregnancies to synchronize.
        :type pregnancies: list[UserPregnancy]
        """
        new_pregnancies_dict = {}
        pregnancies_to_add, existing_pregnancy_ids = [], []
        existing_pregnancies = await self.get_all_pregnancy()  # Get all existing records
        for pregnancy in pregnancies:
            pregnancy_key = (pregnancy.user_id, pregnancy.chat_id)
            new_pregnancies_dict.update({pregnancy_key: pregnancy})

        for pregnancy in existing_pregnancies:
            pregnancy_key = (pregnancy.user_id, pregnancy.chat_id)
            if pregnancy_key in new_pregnancies_dict:
                existing_pregnancy_ids.append(pregnancy_key)
                pregnancy.pdr_date = new_pregnancies_dict[pregnancy_key].pdr_date
                pregnancy.period_date = new_pregnancies_dict[pregnancy_key].period_date
                pregnancy.gender = new_pregnancies_dict[pregnancy_key].gender

        for pregnancy_key, pregnancy in new_pregnancies_dict.items():
            if pregnancy_key not in existing_pregnancy_ids:
                pregnancies_to_add.append(pregnancy)

        if pregnancies_to_add:
            self.connection.add_all(pregnancies_to_add)

        await self.connection.commit()

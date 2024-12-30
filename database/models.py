import os
from database.session import Base
from sqlalchemy.orm import relationship
from sqlalchemy import Boolean, String, ForeignKey, DateTime, BigInteger, Column, Integer


class User(Base):
    """Represents a user in the system"""
    __tablename__ = os.getenv('USERS_TABLE')  # Different tables for different bots

    id = Column(BigInteger, primary_key=True, comment='Unique Telegram user ID')
    full_name = Column(String, default='', nullable=False, comment='User full name (firstname + lastname)')
    username = Column(String(50), default='', nullable=True, comment='User username')
    language = Column(String(2), default='ru', nullable=False, comment='User language')
    reaction = Column(Boolean, default=False, nullable=False, comment='Is the bot blocked by the user')
    google_row_id = Column(Integer, default=1, nullable=False, comment='User row ID in Google Sheets')
    needs_backup_update = Column(
        Boolean, default=False, nullable=False, comment='Flag to update user row in Google Sheets'
    )

    user_pregnancy = relationship('UserPregnancy', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return (
            f'<User(id={self.id}, '
            f'full_name={self.full_name!r}, '
            f'username={self.username!r}, '
            f'language={self.language!r}, '
            f'reaction={self.reaction}, '
            f'google_row_id={self.google_row_id}, '
            f'needs_backup_update={self.needs_backup_update})>'
        )


class UserPregnancy(Base):
    """Represents a user's PRD date"""
    __tablename__ = os.getenv('USER_PREGNANCIES_TABLE')  # Different tables for different bots

    id = Column(BigInteger, primary_key=True, comment='Unique date ID and Google Sheets row ID')
    user_id = Column(BigInteger, ForeignKey(f"{os.getenv('USERS_TABLE')}.id"), nullable=False, comment='User ID')
    chat_id = Column(BigInteger, default=0, nullable=False, comment='Telegram chat ID')
    pdr_date = Column(DateTime, default=None, nullable=True, comment='Date of PDR (UTC+3)')
    period_date = Column(DateTime, default=None, nullable=True, comment='Pregnancy period date (UTC+3)')
    gender = Column(Integer, default=None, nullable=True, comment='Gender of the child, 1 - boy, 2 - girl')
    needs_backup_update = Column(
        Boolean, default=False, nullable=False, comment='Flag to update date row in Google Sheets'
    )

    user = relationship('User', back_populates='user_pregnancy')

    def __repr__(self):
        return (
            f'<UserPregnancy(id={self.id}, '
            f'user_id={self.user_id}, '
            f'chat_id={self.chat_id}, '
            f'pdr_date={self.pdr_date!r}, '
            f'period_date={self.period_date!r}, '
            f'gender={self.period_date!r}, '
            f'needs_backup_update={self.needs_backup_update})>'
        )


class Texts(Base):
    """Stores text content in different languages for the system"""
    __tablename__ = 'texts'

    id = Column(Integer, primary_key=True, comment='Unique identifier')
    text_id = Column(String(500), comment='Text identifier')
    language = Column(String(2), nullable=False, comment='Text language code')
    content = Column(String, nullable=False, comment='The text content')

    def __repr__(self):
        return (
            f'<TextStrings(id={self.id}, '
            f'text_id={self.text_id!r}, '
            f'language={self.language!r}, '
            f'content={self.content!r})>'
        )


class Log(Base):
    """Represents a log entry for a post in the system"""
    __tablename__ = 'log'

    id = Column(Integer, primary_key=True, comment='Unique identifier')
    post_id = Column(Integer, nullable=True, comment='Post ID in the log channel. Filled after publication.')
    post_date = Column(DateTime, nullable=True, comment='Post date in the log channel (UTC)')
    text = Column(String, comment='Логи')

    def __repr__(self):
        return (
            f'<Log(id={self.id}, '
            f'post_id={self.post_id}, '
            f'post_date={self.post_date!r}, '
            f'text={self.text!r})>'
        )

import json
import typing
from functions.base_path import base_path
from google.oauth2.service_account import Credentials
from gspread_asyncio import (
    AsyncioGspreadClientManager, AsyncioGspreadClient, AsyncioGspreadSpreadsheet, AsyncioGspreadWorksheet
)

# Load credentials for Google Sheets API
with open(base_path.joinpath('credentials', 'creds.json'), 'r') as file:
    CREDENTIALS = Credentials.from_service_account_info(
        info=json.load(file),
        scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    )


class GoogleSheetsSession:
    """
    A singleton class to manage interactions with the Google Sheets API.

    This class provides methods to authenticate, retrieve spreadsheets, and access specific worksheets
    using asynchronous operations. It ensures that only one instance of the session is created and reused
    across the application to optimize performance and resource usage.
    """
    _instance = None  # Attribute to store the single class instance

    def __new__(cls, *args, **kwargs):
        """
        Ensures that only one instance of the class is created.

        :return: The single instance of the class.
        :rtype: GoogleSheetsSession
        """
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """Initialize the session only once"""
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.client = None

    @staticmethod
    def get_credentials():
        """Return the credentials for Google Sheets API"""
        return CREDENTIALS

    async def get_client(self) -> AsyncioGspreadClient:
        """
        Creates and returns the Google Sheets API client if it doesn't exist.

        This method authorizes and creates the client only once. If the client has been created
        already, it simply returns the existing client.

        :return: The authorized Google Sheets API client
        :rtype: AsyncioGspreadClient
        """
        if not self.client:
            self.client = await AsyncioGspreadClientManager(self.get_credentials).authorize()
        return self.client

    async def get_spreadsheet(self, sheet_id: str) -> AsyncioGspreadSpreadsheet:
        """
        Retrieves the spreadsheet object by its sheet_id.

        This method opens the spreadsheet using the provided sheet_id, which is the unique identifier
        for the Google Sheets document.

        :param sheet_id: The unique identifier for the Google Sheets document
        :type sheet_id: str
        :return: The Google Sheets spreadsheet object
        :rtype: AsyncioGspreadSpreadsheet
        """
        client = await self.get_client()
        return await client.open_by_key(sheet_id)

    async def get_worksheet(
        self,
        spreadsheet: typing.Union[str, AsyncioGspreadSpreadsheet],
        worksheet_name: str,
    ) -> AsyncioGspreadWorksheet:
        """
        Retrieves a specific worksheet by its name from the provided spreadsheet.

        This method checks if the spreadsheet is provided as a string (sheet_id) or as an already
        opened spreadsheet object. It then fetches the worksheet based on the given name.

        :param spreadsheet: The Google Sheets document (either by sheet_id or spreadsheet object)
        :type spreadsheet: str or AsyncioGspreadSpreadsheet
        :param worksheet_name: The name of the worksheet to retrieve
        :type worksheet_name: str
        :return: The requested worksheet object
        :rtype: AsyncioGspreadWorksheet
        """
        if type(spreadsheet) is str:
            spreadsheet = await self.get_spreadsheet(spreadsheet)
        worksheet = await spreadsheet.worksheet(worksheet_name)
        return worksheet

# st_aggrid/google_sheets_export.py
from typing import Dict, Any, Optional
import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build


class GoogleSheetsExport:
    def __init__(self, google_sheets_creds: Optional[Dict] = None):
        """
        Initialize Google Sheets export functionality.

        Args:
            google_sheets_creds: Google service account credentials
        """
        self.google_sheets_creds = google_sheets_creds
        self._sheets_service = None
        self._drive_service = None

    def _initialize_services(self):
        """Initialize Google Sheets and Drive services."""
        if not self._sheets_service or not self._drive_service:
            credentials = service_account.Credentials.from_service_account_info(
                self.google_sheets_creds,
                scopes=['https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive']
            )

            self._sheets_service = build('sheets', 'v4', credentials=credentials)
            self._drive_service = build('drive', 'v3', credentials=credentials)

    def export_data(self, value: Dict[str, Any]) -> None:
        """
        Export data to Google Sheets.

        Args:
            value: Dictionary containing export configuration and data
        """
        if not self.google_sheets_creds:
            st.error("Google Sheets credentials not configured")
            return

        try:
            self._initialize_services()

            # Create and configure spreadsheet
            spreadsheet_id = self._create_spreadsheet(value.get('filename'))
            self._update_spreadsheet_data(spreadsheet_id, value)
            self._apply_formatting(spreadsheet_id, value)

            # Share if email provided
            if value.get('email'):
                self._share_spreadsheet(spreadsheet_id, value['email'])

            # Show success message
            url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}'
            st.success(f"Exported to Google Sheets! [Open]({url})")

        except Exception as e:
            st.error(f"Export failed: {str(e)}")

    def _create_spreadsheet(self, filename: Optional[str] = None) -> str:
        """Create a new Google Spreadsheet."""
        title = filename or f"AG-Grid Export {pd.Timestamp.now()}"
        spreadsheet = self._sheets_service.spreadsheets().create(
            body={'properties': {'title': title}},
            fields='spreadsheetId'
        ).execute()
        return spreadsheet.get('spreadsheetId')

    def _update_spreadsheet_data(self, spreadsheet_id: str, value: Dict[str, Any]) -> None:
        """Update spreadsheet with data."""
        # Process data based on format type
        if value.get('format') == 'raw':
            export_data = value.get('raw_data')
        else:
            export_data = pd.read_csv(value['data'])

        # Convert to list of lists for Google Sheets API
        if isinstance(export_data, pd.DataFrame):
            values = [export_data.columns.tolist()]
            values.extend(export_data.values.tolist())
        else:
            values = export_data

        self._sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='A1',
            valueInputOption='RAW',
            body={'values': values}
        ).execute()

    def _apply_formatting(self, spreadsheet_id: str, value: Dict[str, Any]) -> None:
        """Apply formatting to the spreadsheet."""
        header_format_request = {
            'repeatCell': {
                'range': {
                    'startRowIndex': 0,
                    'endRowIndex': 1,
                },
                'cell': {
                    'userEnteredFormat': {
                        'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                        'textFormat': {'bold': True}
                    }
                },
                'fields': 'userEnteredFormat(backgroundColor,textFormat)'
            }
        }

        # Get number of columns from the data
        num_columns = len(value.get('data', [])[0]) if value.get('data') else 10

        auto_resize_request = {
            'autoResizeDimensions': {
                'dimensions': {
                    'dimension': 'COLUMNS',
                    'startIndex': 0,
                    'endIndex': num_columns
                }
            }
        }

        self._sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': [header_format_request, auto_resize_request]}
        ).execute()

    def _share_spreadsheet(self, spreadsheet_id: str, email: str) -> None:
        """Share the spreadsheet with specified email."""
        self._drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={
                'type': 'user',
                'role': 'writer',
                'emailAddress': email
            },
            sendNotificationEmail=True
        ).execute()
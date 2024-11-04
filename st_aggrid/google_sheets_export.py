# st_aggrid/google_sheets_export.py
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime


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
        self._auto_export = None

        # Initialize session state for spreadsheet ID if not exists
        if 'gsheets_export_id' not in st.session_state:
            st.session_state.gsheets_export_id = None
            st.session_state.gsheets_export_sheet_count = 0

    def _initialize_services(self):
        """Initialize Google Sheets and Drive services."""
        if not self._sheets_service or not self._drive_service:
            if not self.google_sheets_creds:
                raise ValueError("Google Sheets credentials not configured")

            credentials = service_account.Credentials.from_service_account_info(
                self.google_sheets_creds,
                scopes=['https://www.googleapis.com/auth/spreadsheets',
                        'https://www.googleapis.com/auth/drive']
            )

            self._sheets_service = build('sheets', 'v4', credentials=credentials)
            self._drive_service = build('drive', 'v3', credentials=credentials)

    def _get_or_create_spreadsheet(self, base_filename: Optional[str] = None) -> Tuple[str, int]:
        """Get existing or create new spreadsheet and return its ID and sheet index."""
        if not st.session_state.gsheets_export_id:
            # Create new spreadsheet
            title = base_filename or f"AG-Grid Export {pd.Timestamp.now()}"
            spreadsheet = self._sheets_service.spreadsheets().create(
                body={'properties': {'title': title}},
                fields='spreadsheetId'
            ).execute()
            st.session_state.gsheets_export_id = spreadsheet.get('spreadsheetId')
            st.session_state.gsheets_export_sheet_count = 1
            return st.session_state.gsheets_export_id, 0

        # Add new sheet to existing spreadsheet
        st.session_state.gsheets_export_sheet_count += 1
        sheet_title = f"Export {st.session_state.gsheets_export_sheet_count}"

        result = self._sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=st.session_state.gsheets_export_id,
            body={
                'requests': [{
                    'addSheet': {
                        'properties': {
                            'title': sheet_title
                        }
                    }
                }]
            }
        ).execute()

        new_sheet_id = result['replies'][0]['addSheet']['properties']['sheetId']
        return st.session_state.gsheets_export_id, new_sheet_id

    def export_data(self, value: Dict[str, Any]) -> Optional[str]:
        """
        Export data to Google Sheets.

        Args:
            value: Dictionary containing export configuration and data

        Returns:
            str: Spreadsheet URL if successful, None otherwise
        """
        if not self.google_sheets_creds:
            st.error("Google Sheets credentials not configured")
            return None

        try:
            self._initialize_services()

            # Get export settings
            if self._auto_export and self._auto_export['enabled']:
                filename = pd.Timestamp.now().strftime(self._auto_export['filename_template'])
                target_email = self._auto_export['target_email']
                export_format = self._auto_export['format']
            else:
                filename = value.get('filename')
                target_email = value.get('email')
                export_format = value.get('format', 'formatted')

            # Get or create spreadsheet
            spreadsheet_id, sheet_id = self._get_or_create_spreadsheet(filename)

            # Get timestamp for sheet name if not provided
            timestamp = datetime.now().strftime("%H:%M:%S")
            sheet_title = f"{export_format.title()} Export {timestamp}"

            # Update sheet title
            if sheet_id != 0:  # Don't rename first sheet
                self._sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        'requests': [{
                            'updateSheetProperties': {
                                'properties': {
                                    'sheetId': sheet_id,
                                    'title': sheet_title
                                },
                                'fields': 'title'
                            }
                        }]
                    }
                ).execute()

            # Update data
            self._update_spreadsheet_data(
                spreadsheet_id=spreadsheet_id,
                value=value,
                format_type=export_format,
                sheet_title=sheet_title
            )

            # Apply formatting
            self._apply_formatting(spreadsheet_id, value, sheet_id)

            # Share if email provided and this is the first export
            if target_email and st.session_state.gsheets_export_sheet_count == 1:
                self._share_spreadsheet(spreadsheet_id, target_email)

            # Generate URL
            url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}'

            # Show success message unless auto export
            if not (self._auto_export and self._auto_export['enabled']):
                st.success(f"Exported to Google Sheets! [Open]({url})")

            return url

        except Exception as e:
            st.error(f"Export failed: {str(e)}")
            return None

    def _update_spreadsheet_data(self, spreadsheet_id: str, value: Dict[str, Any],
                                 format_type: str, sheet_title: str) -> None:
        """Update spreadsheet with data."""
        # Process data based on format type
        if format_type == 'raw':
            export_data = value.get('raw_data')
        else:
            export_data = pd.read_csv(value['data'])

        # Convert to list of lists for Google Sheets API
        if isinstance(export_data, pd.DataFrame):
            values = [export_data.columns.tolist()]
            values.extend(export_data.values.tolist())
        else:
            values = export_data

        # Update data in the specific sheet
        range_name = f"'{sheet_title}'!A1"
        self._sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body={'values': values}
        ).execute()

    def _apply_formatting(self, spreadsheet_id: str, value: Dict[str, Any], sheet_id: int) -> None:
        """Apply formatting to the specified sheet."""
        header_format_request = {
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
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

        auto_resize_request = {
            'autoResizeDimensions': {
                'dimensions': {
                    'sheetId': sheet_id,
                    'dimension': 'COLUMNS',
                    'startIndex': 0,
                    'endIndex': 100  # Adjust if you need more columns
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
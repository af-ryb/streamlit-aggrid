import { GoogleAuth } from 'google-auth-library';
import { sheets_v4, drive_v3, google } from 'googleapis';

export interface GoogleSheetsConfig {
    credentials: any;
    userEmail: string;
    sessionId: string;
    timestamp: number;
}

export class GoogleSheetsService {
    private sheetsService!: sheets_v4.Sheets; // Using definite assignment assertion
    private driveService!: drive_v3.Drive; // Using definite assignment assertion
    private config: GoogleSheetsConfig;
    private spreadsheetId: string | null = null;

    constructor(config: GoogleSheetsConfig) {
        this.config = config;
        // Initialize services immediately
        this.initializeServices().catch(error => {
            console.error('Failed to initialize Google services:', error);
            throw error;
        });
    }

    private async initializeServices(): Promise<void> {
        try {
            const auth = new GoogleAuth({
                credentials: this.config.credentials,
                scopes: [
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
            });

            this.sheetsService = google.sheets({ version: 'v4', auth });
            this.driveService = google.drive({ version: 'v3', auth });
        } catch (error) {
            console.error('Failed to initialize services:', error);
            throw error;
        }
    }

    private async getOrCreateSpreadsheet(): Promise<string> {
        // Try to get existing spreadsheet from localStorage
        const storageKey = `gsheets_${this.config.sessionId}`;
        const stored = localStorage.getItem(storageKey);

        if (stored) {
            const { id, timestamp } = JSON.parse(stored);
            if (timestamp === this.config.timestamp) {
                return id;
            }
        }

        // Create new spreadsheet
        const response = await this.sheetsService.spreadsheets.create({
            requestBody: {
                properties: {
                    title: `AG-Grid Export ${new Date().toLocaleString()}`
                }
            }
        });

        const spreadsheetId = response.data.spreadsheetId;
        if (!spreadsheetId) {
            throw new Error('Failed to create spreadsheet: No ID returned');
        }

        // Store in localStorage
        localStorage.setItem(storageKey, JSON.stringify({
            id: spreadsheetId,
            timestamp: this.config.timestamp
        }));

        // Share with user
        if (this.config.userEmail) {
            await this.shareSpreadsheet(spreadsheetId);
        }

        return spreadsheetId;
    }

    private async shareSpreadsheet(spreadsheetId: string): Promise<void> {
        await this.driveService.permissions.create({
            fileId: spreadsheetId,
            requestBody: {
                type: 'user',
                role: 'writer',
                emailAddress: this.config.userEmail
            }
        });
    }

    private async addNewSheet(title: string): Promise<number> {
        if (!this.spreadsheetId) {
            throw new Error('Spreadsheet ID not set');
        }

        const response = await this.sheetsService.spreadsheets.batchUpdate({
            spreadsheetId: this.spreadsheetId,
            requestBody: {
                requests: [{
                    addSheet: {
                        properties: { title }
                    }
                }]
            }
        });

        const sheetId = response.data.replies?.[0]?.addSheet?.properties?.sheetId;
        if (typeof sheetId !== 'number') {
            throw new Error('Failed to create new sheet: No valid sheet ID returned');
        }

        return sheetId;
    }

    public async exportData(data: any[][], format: 'raw' | 'formatted' = 'formatted'): Promise<string> {
        try {
            // Get or create spreadsheet
            this.spreadsheetId = await this.getOrCreateSpreadsheet();

            // Create new sheet
            const sheetTitle = `${format} Export ${new Date().toLocaleTimeString()}`;
            const sheetId = await this.addNewSheet(sheetTitle);

            // Update data
            await this.sheetsService.spreadsheets.values.update({
                spreadsheetId: this.spreadsheetId,
                range: `'${sheetTitle}'!A1`,
                valueInputOption: 'RAW',
                requestBody: { values: data }
            });

            // Apply formatting
            await this.sheetsService.spreadsheets.batchUpdate({
                spreadsheetId: this.spreadsheetId,
                requestBody: {
                    requests: [
                        {
                            repeatCell: {
                                range: {
                                    sheetId,
                                    startRowIndex: 0,
                                    endRowIndex: 1
                                },
                                cell: {
                                    userEnteredFormat: {
                                        backgroundColor: { red: 0.9, green: 0.9, blue: 0.9 },
                                        textFormat: { bold: true }
                                    }
                                },
                                fields: 'userEnteredFormat(backgroundColor,textFormat)'
                            }
                        },
                        {
                            autoResizeDimensions: {
                                dimensions: {
                                    sheetId,
                                    dimension: 'COLUMNS',
                                    startIndex: 0,
                                    endIndex: data[0].length
                                }
                            }
                        }
                    ]
                }
            });

            return `https://docs.google.com/spreadsheets/d/${this.spreadsheetId}`;
        } catch (error) {
            console.error('Export failed:', error);
            throw new Error(error instanceof Error ? error.message : 'Unknown export error');
        }
    }
}
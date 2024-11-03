import { GridApi } from '@ag-grid-community/core';

interface ExportParams {
    api: GridApi;
    context: {
        userEmail?: string;
        componentParent?: any;
    };
}

// Define the expected context structure
interface GridContext {
    userEmail?: string;
    componentParent?: {
        pushValue: (value: any) => void;
    };
}

/**
 * Returns menu items configuration for Google Sheets export
 */
export const getGoogleSheetsMenuItems = () => {
    return [
        {
            name: 'Export to Google Sheets',
            subMenu: [
                {
                    name: 'Raw Data',
                    action: (params: ExportParams) => exportToGoogleSheets(params, 'raw'),
                    icon: '<i class="fas fa-table"></i>'
                },
                {
                    name: 'Formatted Data',
                    action: (params: ExportParams) => exportToGoogleSheets(params, 'formatted'),
                    icon: '<i class="fas fa-file-excel"></i>'
                }
            ]
        }
    ];
};

/**
 * Handles the export to Google Sheets functionality
 */
export const exportToGoogleSheets = (params: ExportParams, format: 'raw' | 'formatted') => {
    // Access context directly from the params
    const context = params.context as GridContext;
    const componentParent = context?.componentParent;

    if (!componentParent) {
        console.error('Component parent not found in grid context');
        return;
    }

    if (format === 'raw') {
        componentParent.pushValue({
            type: 'export_to_gsheets',
            format: 'raw',
            email: context?.userEmail
        });
    } else {
        const csvContent = params.api.getDataAsCsv({
            processCellCallback: (params: any) => {
                return params.value === null || params.value === undefined
                  ? ''
                  : params.value;
            }
        });

        componentParent.pushValue({
            type: 'export_to_gsheets',
            format: 'formatted',
            data: csvContent,
            email: context?.userEmail
        });
    }
};
import {
    GetContextMenuItemsParams,
    MenuItemDef,
    IMenuActionParams,
    ColDef
} from '@ag-grid-community/core';
import { GoogleSheetsService, type GoogleSheetsConfig } from './googleSheetsService';

const getAllGridData = (params: IMenuActionParams): any[][] => {
    const columnDefs = params.api.getColumnDefs();
    if (!columnDefs) {
        throw new Error('No column definitions found');
    }

    // Extract headers from column definitions
    const headers = columnDefs.map((col: ColDef) => col.headerName || col.field || '');

    // Collect all row data
    const allRows: any[] = [];
    params.api.forEachNode((node) => {
        if (node.data) {
            allRows.push(node.data);
        }
    });

    return [headers, ...allRows];
};

const exportToGSheets = (format: 'raw' | 'formatted') => async (params: IMenuActionParams) => {
    try {
        const config = params.context.googleSheetsConfig as GoogleSheetsConfig;
        if (!config) {
            throw new Error('Google Sheets configuration not found');
        }

        const service = new GoogleSheetsService(config);

        // Prepare data based on format
        let data: any[][];
        if (format === 'raw') {
            data = getAllGridData(params);
        } else {
            const csvContent = params.api.getDataAsCsv({
                processCellCallback: (params: any) => {
                    return params.value === null || params.value === undefined
                      ? ''
                      : params.value;
                }
            });

            if (!csvContent) {
                throw new Error('Failed to get CSV content from grid');
            }

            data = csvContent.split('\n')
              .filter(line => line.trim().length > 0) // Filter out empty lines
              .map(line => line.split(','));
        }

        // Export to Google Sheets
        const url = await service.exportData(data, format);

        // Notify success through componentParent
        const componentParent = params.context.componentParent;
        if (componentParent?.pushValue) {
            componentParent.pushValue({
                type: 'google_sheets_success',
                url
            });
        }
    } catch (error) {
        console.error('Export failed:', error);
        const componentParent = params.context.componentParent;
        if (componentParent?.pushValue) {
            componentParent.pushValue({
                type: 'google_sheets_error',
                error: error instanceof Error ? error.message : 'Unknown export error'
            });
        }
    }
};

type ExistingMenuItemsType = (string | MenuItemDef)[] | ((params: GetContextMenuItemsParams) => (string | MenuItemDef)[]);

export const integrateGoogleSheetsMenu = (
  params: GetContextMenuItemsParams,
  existingGetContextMenuItems?: ExistingMenuItemsType
): (string | MenuItemDef)[] => {
    // Only add menu items if Google Sheets is enabled
    if (!params.context?.enableGoogleSheets) {
        return existingGetContextMenuItems ?
          (typeof existingGetContextMenuItems === 'function' ?
            existingGetContextMenuItems(params) : existingGetContextMenuItems) :
          [];
    }

    const gSheetsSubMenu: MenuItemDef = {
        name: 'Export to Google Sheets',
        subMenu: [
            {
                name: 'Raw Data',
                action: exportToGSheets('raw'),
                icon: '<i class="fas fa-table"></i>'
            },
            {
                name: 'Formatted Data',
                action: exportToGSheets('formatted'),
                icon: '<i class="fas fa-file-excel"></i>'
            }
        ]
    };

    const defaultItems = existingGetContextMenuItems ?
      (typeof existingGetContextMenuItems === 'function' ?
        existingGetContextMenuItems(params) : existingGetContextMenuItems) :
      ['copy', 'copyWithHeaders', 'paste'];

    // Add to existing Export menu or create new one
    const exportMenuIndex = defaultItems.findIndex(item =>
      typeof item === 'object' && 'name' in item && item.name === 'Export'
    );

    if (exportMenuIndex >= 0) {
        const exportMenuItem = defaultItems[exportMenuIndex] as MenuItemDef;
        if (!exportMenuItem.subMenu) {
            exportMenuItem.subMenu = [];
        }
        (exportMenuItem.subMenu as MenuItemDef[]).push(gSheetsSubMenu);
    } else {
        defaultItems.push(gSheetsSubMenu);
    }

    return defaultItems;
};
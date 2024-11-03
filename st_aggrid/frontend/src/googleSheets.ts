// st_aggrid/frontend/src/features/export/googleSheets.ts
import {
    GetContextMenuItemsParams,
    MenuItemDef,
    IMenuActionParams
} from '@ag-grid-community/core';

const exportToGSheets = (format: 'raw' | 'formatted') => (params: IMenuActionParams) => {
    const componentParent = params.context.componentParent;
    const userEmail = params.context?.userEmail || null;  // Handle None/null case

    if (format === 'raw') {
        componentParent.pushValue({
            type: 'export_to_gsheets',
            format: 'raw',
            email: userEmail
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
            email: userEmail
        });
    }
};

const getDefaultMenuItems = (): (string | MenuItemDef)[] => [
    'copy',
    'copyWithHeaders',
    'copyWithGroupHeaders',
    'paste',
    'separator'
];

export const integrateGoogleSheetsMenu = (params: GetContextMenuItemsParams, existingMenuItems?: (string | MenuItemDef)[] | ((params: GetContextMenuItemsParams) => (string | MenuItemDef)[])): (string | MenuItemDef)[] => {
    // Get default or existing menu items
    let defaultItems: (string | MenuItemDef)[];
    if (typeof existingMenuItems === 'function') {
        defaultItems = existingMenuItems(params);
    } else if (Array.isArray(existingMenuItems)) {
        defaultItems = existingMenuItems;
    } else {
        defaultItems = getDefaultMenuItems();
    }

    const gSheetsSubMenu = {
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
    } as MenuItemDef;

    // Find existing Export menu item
    const exportMenuIndex = defaultItems.findIndex(item =>
      typeof item === 'object' && item.name === 'Export'
    );

    if (exportMenuIndex >= 0) {
        // Add to existing Export submenu
        const exportMenuItem = defaultItems[exportMenuIndex] as MenuItemDef;
        if (!exportMenuItem.subMenu) {
            exportMenuItem.subMenu = [];
        }
        (exportMenuItem.subMenu as MenuItemDef[]).push(gSheetsSubMenu);
    } else {
        // Create new Export menu item
        defaultItems.push({
            name: 'Export',
            subMenu: [
                'csvExport',
                'excelExport',
                gSheetsSubMenu
            ]
        } as MenuItemDef);
    }

    return defaultItems;
};
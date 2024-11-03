// st_aggrid/frontend/src/features/export/googleSheets.ts
import {
    GetContextMenuItemsParams,
    GridApi,
    MenuItemDef,
    IMenuActionParams
} from '@ag-grid-community/core';

interface ExportParams extends IMenuActionParams {
    api: GridApi;
    context: any;
}

export const getGoogleSheetsMenuItems = (params: GetContextMenuItemsParams): (string | MenuItemDef)[] => {
    const exportToGSheets = (format: 'raw' | 'formatted') => (actionParams: IMenuActionParams) => {
        const componentParent = actionParams.context.componentParent;

        if (format === 'raw') {
            componentParent.pushValue({
                type: 'export_to_gsheets',
                format: 'raw',
                email: actionParams.context?.userEmail
            });
        } else {
            const csvContent = actionParams.api.getDataAsCsv({
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
                email: actionParams.context?.userEmail
            });
        }
    };

    const menuItems: (string | MenuItemDef)[] = [
        'copy',
        'copyWithHeaders',
        'copyWithGroupHeaders',
        'paste',
        'separator',
        {
            name: 'Export',
            subMenu: [
                'csvExport',
                'excelExport',
                {
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
                } as MenuItemDef
            ]
        } as MenuItemDef
    ];

    return menuItems;
};
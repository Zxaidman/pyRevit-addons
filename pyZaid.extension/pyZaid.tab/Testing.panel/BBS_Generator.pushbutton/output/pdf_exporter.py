# -*- coding: utf-8 -*-
"""
output/pdf_exporter.py
Exports the BBS Excel workbook to PDF safely in PythonNet 3 with Fit-to-Page settings.
"""

import os

def export_pdf(xlsx_path: str, pdf_path: str = None) -> tuple:
    if not os.path.exists(xlsx_path):
        return False, f"Excel file not found: {xlsx_path}", None

    if pdf_path is None:
        base, _ = os.path.splitext(xlsx_path)
        pdf_path = base + ".pdf"

    try:
        # First attempt: win32com (Fastest and safest)
        import win32com.client
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        
        wb = excel.Workbooks.Open(xlsx_path)
        for sheet in wb.Sheets:
            sheet.PageSetup.Zoom = False
            sheet.PageSetup.FitToPagesWide = 1
            sheet.PageSetup.FitToPagesTall = False
            sheet.PageSetup.Orientation = 2 # 2 = Landscape
            
        wb.ExportAsFixedFormat(0, pdf_path)
        wb.Close(False)
        excel.Quit()
        return True, f"PDF saved: {pdf_path}", pdf_path
        
    except ImportError:
        # Second attempt: .NET Fallback
        try:
            import System
            from System import Type, Activator, Reflection
            
            excel_type = Type.GetTypeFromProgID("Excel.Application")
            if not excel_type:
                return False, "Microsoft Excel COM interface not found.", None

            excel_app = Activator.CreateInstance(excel_type)
            
            def _args(*vals):
                arr = System.Array.CreateInstance(System.Object, len(vals))
                for i, v in enumerate(vals): arr[i] = v
                return arr

            excel_type.InvokeMember("Visible", Reflection.BindingFlags.SetProperty, None, excel_app, _args(False))
            excel_type.InvokeMember("DisplayAlerts", Reflection.BindingFlags.SetProperty, None, excel_app, _args(False))
            
            workbooks = excel_type.InvokeMember("Workbooks", Reflection.BindingFlags.GetProperty, None, excel_app, None)
            workbook = workbooks.GetType().InvokeMember("Open", Reflection.BindingFlags.InvokeMethod, None, workbooks, _args(xlsx_path))
            
            # Note: Modifying PageSetup via Reflection is very slow, we rely on default scaling here.
            workbook.GetType().InvokeMember("ExportAsFixedFormat", Reflection.BindingFlags.InvokeMethod, None, workbook, _args(0, pdf_path))
            workbook.GetType().InvokeMember("Close", Reflection.BindingFlags.InvokeMethod, None, workbook, _args(False))
            
            excel_type.InvokeMember("Quit", Reflection.BindingFlags.InvokeMethod, None, excel_app, None)
            System.Runtime.InteropServices.Marshal.ReleaseComObject(excel_app)

            return True, f"PDF saved via .NET: {pdf_path}", pdf_path
            
        except Exception as net_ex:
            return False, f"PDF export failed (.NET): {net_ex}", None
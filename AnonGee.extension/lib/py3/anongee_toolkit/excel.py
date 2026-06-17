# -*- coding: utf-8 -*-
import System
from System import Activator, Type, Array, Object, Reflection
from anongee_toolkit.utils import create_com_array

class ExcelComWriter:
    """
    A late-bound COM wrapper for Excel.
    Features robust Reflection-based callbacks to bypass strict pythonnet bindings.
    """
    def __init__(self, visible=False):
        try:
            excel_type = Type.GetTypeFromProgID("Excel.Application")
            if not excel_type:
                raise RuntimeError("Microsoft Excel is not installed.")
                
            self.app = Activator.CreateInstance(excel_type)
            self.app.DisplayAlerts = False
            self.app.ScreenUpdating = False
            self.app.Visible = visible
            
            try: self.app.SheetsInNewWorkbook = 1
            except Exception: pass
                
            self.workbook = self.app.Workbooks.Add()
            self._initial_sheets = [self.workbook.Worksheets[i+1] for i in range(self.workbook.Worksheets.Count)]
        except Exception as e:
            raise RuntimeError("Failed to initialize Excel COM: {}".format(e))

    def add_sheet(self, name):
        """Adds a new sheet to the workbook."""
        ws = self.workbook.Worksheets.Add(After=self.workbook.Worksheets[self.workbook.Worksheets.Count])
        ws.Name = name
        return ws

    def write_array(self, ws, top_row, left_col, data):
        """Writes a 2D Python list to an Excel range using COM Array."""
        if not data or not data[0]: return None
        num_rows, num_cols = len(data), len(data[0])
        
        arr = Array.CreateInstance(Object, num_rows, num_cols)
        for r in range(num_rows):
            for c in range(num_cols):
                arr[r, c] = data[r][c]
                
        rng = ws.Range[ws.Cells[top_row, left_col], ws.Cells[top_row + num_rows - 1, left_col + num_cols - 1]]
        rng.Value2 = arr
        return rng

    def autofit_columns(self, ws):
        """Applies exact column AutoFit using robust COM Reflection."""
        try:
            ws.Columns.AutoFit()
        except Exception:
            fg = Reflection.BindingFlags.GetProperty
            fi = Reflection.BindingFlags.InvokeMethod
            wst = ws.GetType()
            cols = wst.InvokeMember("Columns", fg, None, ws, None)
            cols.GetType().InvokeMember("AutoFit", fi, None, cols, None)

    def format_page_landscape(self, ws):
        """Sets worksheet to Landscape and Fit-to-1-Page-Wide."""
        try:
            ws.PageSetup.Orientation = 2 # xlLandscape
            ws.PageSetup.FitToPagesWide = 1
            ws.PageSetup.FitToPagesTall = False
        except Exception:
            fg = Reflection.BindingFlags.GetProperty
            fs = Reflection.BindingFlags.SetProperty
            wst = ws.GetType()
            ps = wst.InvokeMember("PageSetup", fg, None, ws, None)
            pst = ps.GetType()
            pst.InvokeMember("Orientation", fs, None, ps, create_com_array(2))
            pst.InvokeMember("Zoom", fs, None, ps, create_com_array(False))
            pst.InvokeMember("FitToPagesWide", fs, None, ps, create_com_array(1))
            pst.InvokeMember("FitToPagesTall", fs, None, ps, create_com_array(False))

    def export_as_pdf(self, pdf_path):
        """Exports the active workbook to PDF using COM Reflection."""
        try:
            self.workbook.ExportAsFixedFormat(0, pdf_path) # 0 = xlTypePDF
        except Exception:
            fi = Reflection.BindingFlags.InvokeMethod
            wbt = self.workbook.GetType()
            wbt.InvokeMember("ExportAsFixedFormat", fi, None, self.workbook, create_com_array(0, pdf_path))

    def cleanup_initial_sheets(self):
        for sheet in self._initial_sheets:
            try: sheet.Delete()
            except Exception: pass

    def save_and_show(self, filepath):
        """Saves as .xlsx, releases objects, and opens Excel window."""
        self.cleanup_initial_sheets()
        try:
            self.workbook.SaveAs(filepath, 51)
        except Exception as e:
            raise IOError("Failed to save to {}: {}".format(filepath, e))
        finally:
            self.app.ScreenUpdating = True
            self.app.DisplayAlerts = True
            self.app.Visible = True

    def close_without_saving(self):
        """Force kills the COM instance silently."""
        try:
            self.workbook.Close(False)
            self.app.Quit()
            System.Runtime.InteropServices.Marshal.ReleaseComObject(self.app)
        except Exception:
            pass
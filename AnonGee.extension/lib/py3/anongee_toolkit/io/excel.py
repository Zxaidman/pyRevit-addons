# -*- coding: utf-8 -*-
"""
Late-bound COM wrapper for Microsoft Excel.

Uses ``System.Activator`` for late binding and ``System.Reflection`` as a
fallback for method calls that strict pythonnet bindings reject, making the
class robust across Excel versions.
"""
import System
from System import Activator, Type, Array, Object
from System import Reflection
from anongee_toolkit.utils.helpers import create_com_array


class ExcelComWriter:
    """
    Drive Excel via COM automation to build and export workbooks.

    Args:
        visible (bool): Whether to show the Excel window during writing.
            Set to ``False`` (default) for background generation.

    Raises:
        RuntimeError: If Excel is not installed or COM instantiation fails.
    """

    def __init__(self, visible=False):
        excel_type = Type.GetTypeFromProgID("Excel.Application")
        if not excel_type:
            raise RuntimeError("Microsoft Excel is not installed on this machine.")

        try:
            self.app = Activator.CreateInstance(excel_type)
        except Exception as exc:
            raise RuntimeError("Failed to start Excel COM: {}".format(exc))

        self.app.DisplayAlerts = False
        self.app.ScreenUpdating = False
        self.app.Visible = visible

        try:
            self.app.SheetsInNewWorkbook = 1
        except Exception:
            pass

        self.workbook = self.app.Workbooks.Add()
        self._initial_sheets = [
            self.workbook.Worksheets[i + 1]
            for i in range(self.workbook.Worksheets.Count)
        ]

    # ------------------------------------------------------------------
    # Sheet management
    # ------------------------------------------------------------------

    def add_sheet(self, name):
        """Add a new worksheet named *name* after the last existing sheet."""
        ws = self.workbook.Worksheets.Add(
            After=self.workbook.Worksheets[self.workbook.Worksheets.Count]
        )
        ws.Name = name
        return ws

    def cleanup_initial_sheets(self):
        """Delete the placeholder sheets that Excel creates with a new workbook."""
        for sheet in self._initial_sheets:
            try:
                sheet.Delete()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Data writing
    # ------------------------------------------------------------------

    def write_array(self, ws, top_row, left_col, data):
        """
        Write a 2-D Python list to an Excel range in a single COM call.

        Args:
            ws: Excel Worksheet COM object.
            top_row (int): 1-based row index of the top-left cell.
            left_col (int): 1-based column index of the top-left cell.
            data (list[list]): Rows of values.

        Returns:
            Range COM object, or ``None`` if *data* is empty.
        """
        if not data or not data[0]:
            return None

        num_rows, num_cols = len(data), len(data[0])
        arr = Array.CreateInstance(Object, num_rows, num_cols)
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                arr[r, c] = val

        rng = ws.Range[
            ws.Cells[top_row, left_col],
            ws.Cells[top_row + num_rows - 1, left_col + num_cols - 1],
        ]
        rng.Value2 = arr
        return rng

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def autofit_columns(self, ws):
        """Auto-fit all column widths on *ws*, with a Reflection fallback."""
        try:
            ws.Columns.AutoFit()
        except Exception:
            fg = Reflection.BindingFlags.GetProperty
            fi = Reflection.BindingFlags.InvokeMethod
            cols = ws.GetType().InvokeMember("Columns", fg, None, ws, None)
            cols.GetType().InvokeMember("AutoFit", fi, None, cols, None)

    def format_page_landscape(self, ws):
        """Set *ws* to landscape orientation, fit-to-1-page-wide."""
        try:
            ws.PageSetup.Orientation = 2       # xlLandscape
            ws.PageSetup.FitToPagesWide = 1
            ws.PageSetup.FitToPagesTall = False
        except Exception:
            fg = Reflection.BindingFlags.GetProperty
            fs = Reflection.BindingFlags.SetProperty
            ps = ws.GetType().InvokeMember("PageSetup", fg, None, ws, None)
            pst = ps.GetType()
            pst.InvokeMember("Orientation",    fs, None, ps, create_com_array(2))
            pst.InvokeMember("Zoom",           fs, None, ps, create_com_array(False))
            pst.InvokeMember("FitToPagesWide", fs, None, ps, create_com_array(1))
            pst.InvokeMember("FitToPagesTall", fs, None, ps, create_com_array(False))

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_as_pdf(self, pdf_path):
        """Export the active workbook as a PDF to *pdf_path*."""
        try:
            self.workbook.ExportAsFixedFormat(0, pdf_path)  # 0 = xlTypePDF
        except Exception:
            fi = Reflection.BindingFlags.InvokeMethod
            self.workbook.GetType().InvokeMember(
                "ExportAsFixedFormat", fi, None, self.workbook,
                create_com_array(0, pdf_path),
            )

    def save_and_show(self, filepath):
        """
        Save the workbook as ``.xlsx``, release COM locks, then show Excel.

        Args:
            filepath (str): Destination path (should end in ``.xlsx``).

        Raises:
            IOError: If saving fails.
        """
        self.cleanup_initial_sheets()
        try:
            self.workbook.SaveAs(filepath, 51)  # 51 = xlOpenXMLWorkbook
        except Exception as exc:
            raise IOError("Failed to save workbook to {}: {}".format(filepath, exc))
        finally:
            self.app.ScreenUpdating = True
            self.app.DisplayAlerts = True
            self.app.Visible = True

    def close_without_saving(self):
        """Discard the workbook and terminate the Excel process silently."""
        try:
            self.workbook.Close(False)
            self.app.Quit()
            System.Runtime.InteropServices.Marshal.ReleaseComObject(self.app)
        except Exception:
            pass

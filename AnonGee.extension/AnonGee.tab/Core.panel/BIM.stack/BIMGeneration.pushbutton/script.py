#! python3
# -*- coding: utf-8 -*-
__title__ = 'BIM Generation Pro'
__author__ = 'AnonGee'

import sys
import os
import traceback

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xml')

from System.Windows.Markup import XamlReader
from System.IO import FileStream, FileMode, FileAccess
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage
import System.Windows.Forms

local_directory = os.path.dirname(os.path.realpath(__file__))
if local_directory not in sys.path:
    sys.path.append(local_directory)

import core
import parser_service

# __revit__ is injected by pyRevit's engine
doc = __revit__.ActiveUIDocument.Document


def _show_error(title, message, detail=None):
    """
    Display a user-facing error message box.
    If detail is provided (e.g. a traceback string) it is appended after a
    separator so engineers can diagnose without restarting Revit.
    """
    body = message
    if detail:
        body += f"\n\n─── Technical detail ───\n{detail}"
    MessageBox.Show(body, title, MessageBoxButton.OK, MessageBoxImage.Error)


# ─────────────────────────────────────────────────────────────────────────────
# InpToBimDialog
#
# UI-thread responsibilities only:
#   • Load and show the WPF window as a blocking modal
#   • Validate user input
#   • Capture confirmed selections into public attributes on success
#   • Close itself — returning control to the Revit API thread
#
# NOT responsible for transactions or model writes.
# ─────────────────────────────────────────────────────────────────────────────
class InpToBimDialog(object):

    def __init__(self):
        # True only when the user clicks Generate with valid inputs
        self.user_confirmed = False

        self.confirmed_input_file   = None
        self.confirmed_col_symbol   = None
        self.confirmed_beam_symbol  = None
        self.confirmed_floor_type   = None
        self.confirmed_level_prefix = None
        self.confirmed_level_start  = None
        self.confirmed_level_suffix = None
        self.confirmed_separator    = None

        xaml_path = os.path.join(local_directory, 'ui.xaml')
        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        except Exception as e:
            _show_error("UI Error", "UI failed to load.", traceback.format_exc())
            return
        finally:
            stream.Close()

        self._bind_named_elements()
        self._load_family_data()
        self._wire_events()

    def _bind_named_elements(self):
        find = self.window.FindName
        self.combo_columns      = find("ComboStructuralColumns")
        self.combo_beams        = find("ComboStructuralBeams")
        self.combo_floors       = find("ComboFloorTypes")
        self.input_file_path    = find("InputFilePathBox")
        self.input_level_prefix = find("LevelPrefixInput")
        self.input_level_base   = find("LevelBaseInput")
        self.input_level_suffix = find("LevelSuffixInput")
        self.input_level_sep    = find("LevelSeparatorInput")
        self.text_level_preview = find("TextLevelPreview")

    def _load_family_data(self):
        self.column_families = core.get_structural_columns(doc)
        self.beam_families   = core.get_structural_framings(doc)
        self.floor_types     = core.get_floor_types(doc)

        if not self.column_families or not self.beam_families or not self.floor_types:
            MessageBox.Show(
                "One or more required family categories are missing from the project.\n"
                "Load structural column, framing, and floor families before running this tool.",
                "Missing Families",
                MessageBoxButton.OK,
                MessageBoxImage.Warning
            )
            self.window.Close()
            return

        for name in self.column_families:
            self.combo_columns.Items.Add(name)
        for name in self.beam_families:
            self.combo_beams.Items.Add(name)
        for name in self.floor_types:
            self.combo_floors.Items.Add(name)

        self.combo_columns.SelectedIndex = 0
        self.combo_beams.SelectedIndex   = 0
        self.combo_floors.SelectedIndex  = 0

    def _wire_events(self):
        self.window.FindName("ButtonBrowsePath").Click += self._on_browse
        self.window.FindName("ButtonCancel").Click     += self._on_cancel
        self.window.FindName("ButtonGenerate").Click   += self._on_generate
        self.input_level_prefix.TextChanged += self._on_level_input_changed
        self.input_level_base.TextChanged   += self._on_level_input_changed
        self.input_level_suffix.TextChanged += self._on_level_input_changed
        self.input_level_sep.TextChanged    += self._on_level_input_changed

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_browse(self, sender, args):
        dialog = System.Windows.Forms.OpenFileDialog()
        dialog.Title  = "Select FRAME INP File"
        dialog.Filter = "INP/TXT files (*.inp;*.txt)|*.inp;*.txt|All files (*.*)|*.*"
        if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
            self.input_file_path.Text = dialog.FileName

    def _on_cancel(self, sender, args):
        # user_confirmed stays False — main block will see this and exit cleanly
        self.window.Close()

    def _on_generate(self, sender, args):
        """
        Validate only — no model writes, no transactions.
        On success: capture selections and close (returns control to API thread).
        """
        target_file = self.input_file_path.Text.strip()

        if not target_file:
            MessageBox.Show(
                "No input file selected. Use Browse to locate the INP file.",
                "Input Required", MessageBoxButton.OK, MessageBoxImage.Warning
            )
            return

        if not os.path.exists(target_file):
            MessageBox.Show(
                f"File not found:\n{target_file}\n\nVerify the path and try again.",
                "File Not Found", MessageBoxButton.OK, MessageBoxImage.Warning
            )
            return

        col_idx   = self.combo_columns.SelectedIndex
        beam_idx  = self.combo_beams.SelectedIndex
        floor_idx = self.combo_floors.SelectedIndex

        if col_idx < 0 or beam_idx < 0 or floor_idx < 0:
            MessageBox.Show(
                "Select a family type for columns, beams, and floors before generating.",
                "Selection Required", MessageBoxButton.OK, MessageBoxImage.Warning
            )
            return

        self.confirmed_input_file   = target_file
        self.confirmed_col_symbol   = list(self.column_families.values())[col_idx]
        self.confirmed_beam_symbol  = list(self.beam_families.values())[beam_idx]
        self.confirmed_floor_type   = list(self.floor_types.values())[floor_idx]
        self.confirmed_level_prefix = self.input_level_prefix.Text.strip()
        self.confirmed_level_start  = self.input_level_base.Text.strip()
        self.confirmed_level_suffix = self.input_level_suffix.Text.strip()
        self.confirmed_separator    = self.input_level_sep.Text
        self.user_confirmed         = True

        self.window.Close()

    def _on_level_input_changed(self, sender, args):
        prefix = self.input_level_prefix.Text.strip()
        base   = self.input_level_base.Text.strip()
        suffix = self.input_level_suffix.Text.strip()
        sep    = self.input_level_sep.Text
        parts  = [p for p in [prefix, base, suffix] if p]
        self.text_level_preview.Text = sep.join(parts) or "—"

    def show(self):
        self.window.ShowDialog()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
#
# The ENTIRE block is wrapped in a top-level except clause.
# Any unhandled exception — import errors, unexpected API failures, anything —
# is caught here, shown to the user as a clean dialog, and the pyRevit CPython
# engine continues running normally. Revit does NOT need to be restarted.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    try:
        dialog = InpToBimDialog()

        # Guard: window failed to load (XAML error or missing families closed it)
        if not hasattr(dialog, 'window'):
            pass
        else:
            dialog.show()  # blocks until the window closes

            if dialog.user_confirmed:

                # Parse INP file — pure read, no API writes, outside transaction
                try:
                    manifest = parser_service.extract_schematics(dialog.confirmed_input_file)
                except Exception:
                    _show_error(
                        "Parse Error",
                        "INP file could not be parsed. Verify the file format and try again.",
                        traceback.format_exc()
                    )
                    manifest = None

                if manifest is not None:
                    # Generation runs on the Revit API thread — transaction starts inside core.py
                    try:
                        core.execute_generation_protocol(
                            doc=doc,
                            parsed_model=manifest,
                            col_symbol=dialog.confirmed_col_symbol,
                            beam_symbol=dialog.confirmed_beam_symbol,
                            floor_type=dialog.confirmed_floor_type,
                            level_prefix=dialog.confirmed_level_prefix,
                            level_start_name=dialog.confirmed_level_start,
                            level_suffix=dialog.confirmed_level_suffix,
                            separator=dialog.confirmed_separator,
                        )
                        MessageBox.Show(
                            "Structural model generated successfully.\n\n"
                            f"Levels: {len(set(c.elevation_bottom_metric for c in manifest['columns']) | set(c.elevation_top_metric for c in manifest['columns']))}\n"
                            f"Columns: {len(manifest['columns'])}\n"
                            f"Beams:   {len(manifest['framings'])}\n"
                            f"Slabs:   {len(manifest['slabs'])}",
                            "Generation Complete",
                            MessageBoxButton.OK,
                            MessageBoxImage.Information
                        )
                    except Exception:
                        _show_error(
                            "Generation Error",
                            "Structural model generation failed. The transaction has been rolled back — no changes were made to the model.",
                            traceback.format_exc()
                        )

    except Exception:
        # Last-resort catch — prevents ANY exception from bubbling up to the
        # pyRevit engine and crashing the CPython session.
        _show_error(
            "Unexpected Error",
            "An unexpected error occurred. The pyRevit engine is still running — you do not need to restart Revit.",
            traceback.format_exc()
        )

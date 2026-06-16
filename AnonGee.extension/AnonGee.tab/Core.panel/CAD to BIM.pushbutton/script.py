# -*- coding: utf-8 -*-
"""CAD to BIM -- linked-DWG reader + grids pass.

Reads a linked CAD, classifies its curves by layer (convention + optional
override), reports the parse, optionally exports the intermediate JSON, and
creates Revit GRIDS from the classified grid lines.

Grids are created inside a TransactionGroup with warning suppression. Columns,
beams and slabs remain later passes and are deliberately absent (not stubbed).

The cad2bim package lives in `lib/py2/`. pyRevit puts `lib/` on sys.path (so
`path_resolver` imports), but NOT the py2/py3 subfolders -- so we call the repo's
`path_resolver.update_paths()` first to inject `lib/py2` before importing cad2bim.
"""

__title__ = "CAD to BIM"
__doc__ = ("Read a linked CAD (DWG), classify its curves by layer, and create "
           "Revit grids from the grid lines. Columns/beams/slabs are later passes.")
__author__ = "AnonGee"
__min_revit_ver__ = 2022

import os
import sys


def _bootstrap_lib_path():
    """Put the engine-appropriate lib subfolder (py2/py3) on sys.path.

    Primary: the repo's own path_resolver, which pyRevit makes importable by
    adding the extension `lib/` folder to sys.path. Fallback: climb from this
    file to find the `lib` dir and inject py2/py3 directly, so the button still
    loads if path_resolver cannot be imported for any reason.
    """
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass

    sub = "py3" if sys.version_info[0] == 3 else "py2"
    try:
        cursor = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return  # no __file__ in this host; rely on whatever is already on path

    for _ in range(8):  # bounded: button -> panel -> tab -> extension -> lib
        candidate = os.path.join(cursor, "lib", sub)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


_bootstrap_lib_path()

from pyrevit import revit, forms, script, HOST_APP
from Autodesk.Revit.DB import Transaction, TransactionGroup
from System.Windows.Controls import Grid as WpfGrid, ColumnDefinition, TextBlock, ComboBox
from System.Windows import Thickness, GridLength, GridUnitType, VerticalAlignment

import cad2bim
from cad2bim import (compat, cad_links, geometry_reader, layers, ui, report,
                     grids, transactions, columns, beams)

logger = script.get_logger()
output = script.get_output()

_XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.xaml")


class CadToBimWindow(forms.WPFWindow):
    """Single capture-only window: edit the layer mapping and pick what to build.

    Holds no Revit API references and performs no model writes -- it only gathers
    the user's choices into self.result and closes. All model work happens after
    show_dialog() returns, on the Revit API thread (the brand's no-blocking rule).
    """

    def __init__(self, source_name, layer_rows, categories, default_mapping,
                 column_symbols, level_options, beam_symbols):
        forms.WPFWindow.__init__(self, _XAML)
        self.result = None
        self._combos = []
        self.version_text.Text = "v{0}".format(cad2bim.__version__)
        self.source_text.Text = source_name
        self._build_rows(layer_rows, categories, default_mapping)
        self._family_ids = self._fill_combo(self.cb_family, column_symbols)
        self._fill_combo(self.cb_circular_family, column_symbols)
        self._level_ids = self._fill_combo(self.cb_base_level, level_options)
        self._fill_combo(self.cb_top_level, level_options)
        self._beam_ids = self._fill_combo(self.cb_beam_family, beam_symbols)
        self._init_sizing()
        if not column_symbols:
            # Fail loud, fail useful: nothing to place into.
            self.chk_columns.IsChecked = False
            self.chk_columns.IsEnabled = False
            self.chk_columns.Content = "Create columns (load a structural column family first)"
        if not beam_symbols:
            self.chk_beams.IsChecked = False
            self.chk_beams.IsEnabled = False
            self.chk_beams.Content = "Create beams (load a structural framing family first)"
        self.btn_run.Click += self.on_run
        self.btn_cancel.Click += self.on_cancel

    def _fill_combo(self, combo, label_id_pairs):
        """Populate a combo with labels; return {label: ElementId}. Selects the first."""
        mapping = {}
        for label, element_id in label_id_pairs:
            combo.Items.Add(label)
            mapping[label] = element_id
        if combo.Items.Count:
            combo.SelectedIndex = 0
        return mapping

    def _build_rows(self, layer_rows, categories, default_mapping):
        combo_style = self.Resources["InputComboBox"]
        mono_font = self.Resources["FontMono"]
        body_size = self.Resources["FontSizeBody"]
        for layer, count in layer_rows:
            row = WpfGrid()
            row.Margin = Thickness(0, 2, 0, 2)
            for width in (None, 70, 150):   # None -> star column
                column = ColumnDefinition()
                column.Width = (GridLength(1, GridUnitType.Star) if width is None
                                else GridLength(width))
                row.ColumnDefinitions.Add(column)

            name_block = TextBlock()
            name_block.Text = layer
            name_block.FontFamily = mono_font
            name_block.FontSize = body_size
            name_block.VerticalAlignment = VerticalAlignment.Center
            WpfGrid.SetColumn(name_block, 0)

            count_block = TextBlock()
            count_block.Text = str(count)
            count_block.FontSize = body_size
            count_block.VerticalAlignment = VerticalAlignment.Center
            WpfGrid.SetColumn(count_block, 1)

            combo = ComboBox()
            combo.Style = combo_style
            for category in categories:
                combo.Items.Add(category)
            combo.SelectedItem = default_mapping.get(layer, layers.CATEGORY_UNMAPPED)
            WpfGrid.SetColumn(combo, 2)

            row.Children.Add(name_block)
            row.Children.Add(count_block)
            row.Children.Add(combo)
            self.layer_rows.Children.Add(row)
            self._combos.append((layer, combo))

    def _init_sizing(self):
        """Seed the limit fields from defaults and two-way link each slider+input."""
        defaults = report.DEFAULT_LIMITS
        pairs = [
            (self.tb_beam_min, self.sl_beam_min, defaults["beam_width_min_mm"]),
            (self.tb_beam_max, self.sl_beam_max, defaults["beam_width_max_mm"]),
            (self.tb_colb_min, self.sl_colb_min, defaults["col_b_min_mm"]),
            (self.tb_colb_max, self.sl_colb_max, defaults["col_b_max_mm"]),
            (self.tb_colh_min, self.sl_colh_min, defaults["col_h_min_mm"]),
            (self.tb_colh_max, self.sl_colh_max, defaults["col_h_max_mm"]),
        ]
        for textbox, slider, value in pairs:
            textbox.Text = str(int(value))
            try:
                slider.Value = float(value)
                self._link(textbox, slider)
            except Exception:
                pass   # a slider hiccup must never break the dialog

    def _link(self, textbox, slider):
        def on_slider(sender, args):
            textbox.Text = str(int(round(slider.Value)))

        def on_text(sender, args):
            try:
                slider.Value = float(textbox.Text)
            except (ValueError, TypeError):
                pass
        slider.ValueChanged += on_slider
        textbox.LostFocus += on_text

    def _read_int(self, textbox, fallback):
        try:
            return int(round(float(textbox.Text)))
        except (ValueError, TypeError):
            return fallback

    def _read_limits(self):
        defaults = report.DEFAULT_LIMITS
        return {
            "beam_width_min_mm": self._read_int(self.tb_beam_min, defaults["beam_width_min_mm"]),
            "beam_width_max_mm": self._read_int(self.tb_beam_max, defaults["beam_width_max_mm"]),
            "col_b_min_mm": self._read_int(self.tb_colb_min, defaults["col_b_min_mm"]),
            "col_b_max_mm": self._read_int(self.tb_colb_max, defaults["col_b_max_mm"]),
            "col_h_min_mm": self._read_int(self.tb_colh_min, defaults["col_h_min_mm"]),
            "col_h_max_mm": self._read_int(self.tb_colh_max, defaults["col_h_max_mm"]),
        }

    def on_run(self, sender, args):
        mapping = {}
        for layer, combo in self._combos:
            mapping[layer] = combo.SelectedItem or layers.CATEGORY_UNMAPPED
        self.result = {
            "mapping": mapping,
            "create_grids": bool(self.chk_grids.IsChecked),
            "create_columns": bool(self.chk_columns.IsChecked),
            "create_beams": bool(self.chk_beams.IsChecked),
            "column_family_id": self._family_ids.get(self.cb_family.SelectedItem),
            "circular_family_id": self._family_ids.get(self.cb_circular_family.SelectedItem),
            "beam_family_id": self._beam_ids.get(self.cb_beam_family.SelectedItem),
            "base_level_id": self._level_ids.get(self.cb_base_level.SelectedItem),
            "top_level_id": self._level_ids.get(self.cb_top_level.SelectedItem),
            "export": bool(self.chk_export.IsChecked),
            "limits": self._read_limits(),
            "standards": {
                "column": report.parse_standard_sizes(self.tb_std_columns.Text),
                "beam_widths": report.parse_standard_widths(self.tb_std_beams.Text),
            },
        }
        self.Close()

    def on_cancel(self, sender, args):
        self.result = None
        self.Close()


def main():
    doc = revit.doc
    if doc is None:
        forms.alert("Open a Revit project before running CAD to BIM.", exitscript=True)
        return

    # Version banner: confirms WHICH cad2bim actually loaded. If the version or
    # path below is not what you expect, a stale or shadowing copy is on sys.path
    # (e.g. a leftover lib/cad2bim hijacking lib/py2/cad2bim) -- reload pyRevit
    # and remove the stray copy.
    module_dir = os.path.dirname(os.path.abspath(report.__file__))
    output.print_md("**cad2bim {0}** loaded from `{1}`".format(cad2bim.__version__, module_dir))
    logger.info("cad2bim {0} from {1}".format(cad2bim.__version__, module_dir))

    # Startup self-check: surfaces the runtime/host so the Revit-2025 IronPython
    # loader situation (a pyRevit 5.1-line issue, reworked in the 6.x line) is
    # visible in the log if anything ever misbehaves.
    logger.info(compat.runtime_summary())
    logger.info("Host: Revit {0}".format(HOST_APP.version))

    links = cad_links.find_cad_links(doc)
    if not links:
        forms.alert("No linked CAD (DWG) found. Link a DWG, then re-run.",
                    exitscript=True)
        return

    chosen_link = ui.pick_link(doc, links)   # stock picker only when >1 link
    if chosen_link is None:
        forms.alert("No link selected -- nothing to read.", exitscript=True)
        return

    read_result = geometry_reader.read_link(doc, chosen_link)
    if read_result.is_empty():
        forms.alert("'{0}' contained no readable curves.".format(read_result.source_name),
                    exitscript=True)
        return

    # Build the window from already-read data; the window touches no Revit API.
    layer_counts = report.build_layer_counts(read_result.records)
    layer_rows = [(name, layer_counts.get(name, {}).get("count", 0))
                  for name in read_result.layer_names]
    default_mapping = layers.build_default_mapping(read_result.layer_names)
    column_symbols = columns.structural_column_symbols(doc)
    level_options = columns.levels(doc)
    beam_symbols = beams.structural_framing_symbols(doc)

    window = CadToBimWindow(read_result.source_name, layer_rows,
                            list(layers.ALL_CATEGORIES), default_mapping,
                            column_symbols, level_options, beam_symbols)
    window.show_dialog()
    if not window.result:
        return  # cancelled -- nothing read or written

    selections = window.result
    layers.apply_mapping(read_result.records, selections["mapping"])
    limits = selections.get("limits")
    standards = selections.get("standards")
    sections = report.build_column_sections(read_result.records, limits, standards)
    beam_segments = report.build_beam_segments(read_result.records,
                                               sections.get("circles"),
                                               limits, standards)

    output.print_md("### CAD to BIM {0}".format(cad2bim.__version__))
    for line in report.format_console(read_result, selections["mapping"],
                                      sections, beam_segments):
        output.print_md("`{0}`".format(line))

    outcomes = {}
    if selections["create_grids"]:
        outcomes["grids"] = _create_grids(doc, read_result.records)
    if selections["create_columns"]:
        outcomes["columns"] = _create_columns(doc, sections, selections)
    if selections["create_beams"]:
        outcomes["beams"] = _create_beams(doc, beam_segments, selections)
    if selections["export"]:
        _export(read_result, selections["mapping"], sections, beam_segments, outcomes)


def _create_grids(doc, records):
    """Create grids from classified grid lines, inside a transaction group.

    Called only when the user ticked "Create grids". All Revit writes happen here
    on the Revit API thread after the window has closed -- never in a UI handler.
    Both the inner transaction and the group roll back on any failure.
    """
    grid_records = [r for r in records
                    if r.category == layers.CATEGORY_GRID and r.kind in ("line", "arc")]
    if not grid_records:
        output.print_md("`Grids -- no grid-category lines to create.`")
        return {"created": 0, "skipped": 0, "errors": 0}

    namer = grids.GridNamer(grid_records)
    group = TransactionGroup(doc, "CAD to BIM: Grids")
    transaction = Transaction(doc, "Create grids")
    group.Start()
    transaction.Start()
    transactions.attach_warning_swallower(transaction)
    try:
        result = grids.create_grids(doc, grid_records, namer)
        transaction.Commit()
        group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        logger.error("Grid creation failed: {0}".format(creation_error))
        forms.alert("Grid creation failed:\n{0}".format(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    output.print_md("`Grids -- created: {0}, skipped: {1}, errors: {2}`".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"]:
        logger.warning("grid: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"])}


def _create_columns(doc, sections, selections):
    """Place rectangular columns from the decomposed sections, in a group.

    Validates the family/level choices first (fail loud), then writes inside a
    TransactionGroup + Transaction with warning suppression and rollback.
    """
    family_id = selections.get("column_family_id")
    base_id = selections.get("base_level_id")
    top_id = selections.get("top_level_id")
    if family_id is None or base_id is None or top_id is None:
        forms.alert("Columns skipped: choose a column family and base/top levels.")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}
    if not sections.get("entries"):
        output.print_md("`Columns -- no column sections to place.`")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Columns")
    transaction = Transaction(doc, "Create columns")
    group.Start()
    transaction.Start()
    transactions.attach_warning_swallower(transaction)
    try:
        result = columns.place_columns(doc, sections, family_id, base_id, top_id)
        circles = sections.get("circles", [])
        circular_id = selections.get("circular_family_id")
        circular = {"created": [], "errors": []}
        if circles and circular_id is not None:
            circular = columns.place_circular_columns(
                doc, circles, circular_id, base_id, top_id)
        elif circles:
            logger.warning("circular columns skipped: no circular family selected")
        transaction.Commit()
        group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        logger.error("Column creation failed: {0}".format(creation_error))
        forms.alert("Column creation failed:\n{0}".format(creation_error))
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 1}

    output.print_md("`Columns -- rect created: {0}, circular: {1}, skipped: {2}, errors: {3}`".format(
        len(result["created"]), len(circular["created"]),
        len(result["skipped"]), len(result["errors"]) + len(circular["errors"])))
    for message in result["errors"] + circular["errors"] + result["skipped"]:
        logger.warning("column: {0}".format(message))
    return {"rect": len(result["created"]), "circular": len(circular["created"]),
            "skipped": len(result["skipped"]),
            "errors": len(result["errors"]) + len(circular["errors"])}


def _create_beams(doc, beam_segments, selections):
    """Place beams along derived centerlines at the columns' top level, in a group."""
    beam_id = selections.get("beam_family_id")
    level_id = selections.get("top_level_id")
    if beam_id is None or level_id is None:
        forms.alert("Beams skipped: choose a beam family and a top level.")
        return {"created": 0, "skipped": 0, "errors": 0}
    segments = beam_segments.get("segments", [])
    if not segments:
        output.print_md("`Beams -- no beam segments to place.`")
        return {"created": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Beams")
    transaction = Transaction(doc, "Create beams")
    group.Start()
    transaction.Start()
    transactions.attach_warning_swallower(transaction)
    try:
        result = beams.place_beams(doc, segments, beam_id, level_id)
        transaction.Commit()
        group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        logger.error("Beam creation failed: {0}".format(creation_error))
        forms.alert("Beam creation failed:\n{0}".format(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    output.print_md("`Beams -- created: {0}, skipped: {1}, errors: {2}`".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"] + result["skipped"]:
        logger.warning("beam: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"])}


def _export(read_result, mapping, sections, beam_segments, outcomes):
    """Write the intermediate JSON (the user already opted in via the window)."""
    target = forms.save_file(file_ext="json", default_name="cad_to_bim_read")
    if not target:
        return
    try:
        report.export_json(target, read_result, mapping, sections,
                           beam_segments, outcomes)
        output.print_md("`Exported JSON (with report) -> {0}`".format(target))
    except (IOError, OSError) as write_error:
        logger.error("JSON export failed: {0}".format(write_error))
        forms.alert("Could not write the JSON file:\n{0}".format(write_error))


if __name__ == "__main__":
    main()

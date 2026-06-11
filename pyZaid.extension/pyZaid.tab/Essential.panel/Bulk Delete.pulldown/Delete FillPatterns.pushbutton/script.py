#! python
# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms, script

doc = revit.doc
output = script.get_output()

def bulk_delete_fill_patterns():
    items_dict = {}

    # Collect Fill Patterns
    try:
        fill_patterns = DB.FilteredElementCollector(doc)\
                          .OfClass(DB.FillPatternElement)\
                          .ToElements()
        for fill_pat in fill_patterns:
            if fill_pat and fill_pat.Name:
                items_dict[fill_pat.Name] = fill_pat
    except Exception as e:
        forms.alert("Could not read Fill Patterns: {}".format(e), exitscript=True)

    if not items_dict:
        forms.alert("No Fill Patterns found in this model.", exitscript=True)

    # Display UI
    selected_names = forms.SelectFromList.show(
        context=sorted(items_dict.keys()),
        title="Select Fill Patterns to Delete",
        width=500,
        height=600,
        multiselect=True,
        button_name="Delete Selected Patterns"
    )

    if not selected_names:
        return

    # Safety Prompt
    if not forms.alert("Delete {} Fill Pattern(s)?\nThis cannot be undone easily.".format(len(selected_names)), yes=True, no=True):
        return

    deleted_count = 0
    skipped_count = 0

    with revit.Transaction("Bulk Delete Fill Patterns"):
        for name in selected_names:
            item = items_dict.get(name)
            if item:
                try:
                    doc.Delete(item.Id)
                    deleted_count += 1
                    print("DELETED: [Fill Pattern] {}".format(name))
                except Exception as err:
                    skipped_count += 1
                    print("SKIPPED: System-locked pattern '{}'. Reason: {}".format(name, err))

    print("\n==================================================")
    print("FILL PATTERN PROCESSING SUMMARY")
    print("==================================================")
    print("Successfully deleted: {}".format(deleted_count))
    print("System-locked skipped: {}".format(skipped_count))
    print("==================================================\n")

if __name__ == "__main__":
    bulk_delete_fill_patterns()

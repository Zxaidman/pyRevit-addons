#! python
# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms, script

doc = revit.doc
output = script.get_output()

def bulk_delete_line_patterns():
    items_dict = {}

    # Collect Line Patterns
    try:
        line_patterns = DB.FilteredElementCollector(doc)\
                          .OfClass(DB.LinePatternElement)\
                          .ToElements()
        for pattern in line_patterns:
            if pattern and pattern.Name:
                items_dict[pattern.Name] = pattern
    except Exception as e:
        forms.alert("Could not read Line Patterns: {}".format(e), exitscript=True)

    if not items_dict:
        forms.alert("No Line Patterns found in this model.", exitscript=True)

    # Display UI
    selected_names = forms.SelectFromList.show(
        context=sorted(items_dict.keys()),
        title="Select Line Patterns to Delete",
        width=500,
        height=600,
        multiselect=True,
        button_name="Delete Selected Patterns"
    )

    if not selected_names:
        return

    # Safety Prompt
    if not forms.alert("Delete {} Line Pattern(s)?\nThis cannot be undone easily.".format(len(selected_names)), yes=True, no=True):
        return

    deleted_count = 0
    skipped_count = 0

    with revit.Transaction("Bulk Delete Line Patterns"):
        for name in selected_names:
            item = items_dict.get(name)
            if item:
                try:
                    doc.Delete(item.Id)
                    deleted_count += 1
                    print("DELETED: [Line Pattern] {}".format(name))
                except Exception as err:
                    skipped_count += 1
                    print("SKIPPED: System-locked pattern '{}'. Reason: {}".format(name, err))

    print("\n==================================================")
    print("LINE PATTERN PROCESSING SUMMARY")
    print("==================================================")
    print("Successfully deleted: {}".format(deleted_count))
    print("System-locked skipped: {}".format(skipped_count))
    print("==================================================\n")

if __name__ == "__main__":
    bulk_delete_line_patterns()

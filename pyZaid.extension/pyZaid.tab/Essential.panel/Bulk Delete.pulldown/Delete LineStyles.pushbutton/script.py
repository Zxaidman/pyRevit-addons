#! python
# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms, script

doc = revit.doc
output = script.get_output()

def bulk_delete_line_styles():
    items_dict = {}

    # Collect Line Styles (Subcategories of OST_Lines)
    try:
        lines_category = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
        for subcategory in lines_category.SubCategories:
            if subcategory and subcategory.Name:
                items_dict[subcategory.Name] = subcategory
    except Exception as e:
        forms.alert("Could not read Line Styles: {}".format(e), exitscript=True)

    if not items_dict:
        forms.alert("No Line Styles found in this model.", exitscript=True)

    # Display UI
    selected_names = forms.SelectFromList.show(
        context=sorted(items_dict.keys()),
        title="Select Line Styles to Delete",
        width=500,
        height=600,
        multiselect=True,
        button_name="Delete Selected Styles"
    )

    if not selected_names:
        return

    # Safety Prompt
    if not forms.alert("Delete {} Line Style(s)?\nThis cannot be undone easily.".format(len(selected_names)), yes=True, no=True):
        return

    deleted_count = 0
    skipped_count = 0

    with revit.Transaction("Bulk Delete Line Styles"):
        for name in selected_names:
            item = items_dict.get(name)
            if item:
                try:
                    doc.Delete(item.Id)
                    deleted_count += 1
                    print("DELETED: [Line Style] {}".format(name))
                except Exception as err:
                    skipped_count += 1
                    print("SKIPPED: System-locked style '{}'. Reason: {}".format(name, err))

    print("\n==================================================")
    print("LINE STYLE PROCESSING SUMMARY")
    print("==================================================")
    print("Successfully deleted: {}".format(deleted_count))
    print("System-locked skipped: {}".format(skipped_count))
    print("==================================================\n")

if __name__ == "__main__":
    bulk_delete_line_styles()

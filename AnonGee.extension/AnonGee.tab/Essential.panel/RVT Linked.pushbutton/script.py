"""Toggles visibility of Revit links on current view."""

from pyrevit import revit, forms
from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
)

OPT_EDIT_TEMPLATE = 'Edit template: stop it from controlling RVT Links'
OPT_REMOVE_TEMPLATE = 'Remove template from this view'


def template_controls_links(view, doc):
    """Check if a view template controls RVT Links visibility."""
    template_id = view.ViewTemplateId
    if template_id == ElementId.InvalidElementId:
        return False  # no template assigned

    template = doc.GetElement(template_id)
    non_controlled = template.GetNonControlledTemplateParameterIds()
    links_param = ElementId(BuiltInParameter.VIS_GRAPHICS_RVT_LINKS)

    return links_param not in non_controlled


def release_links_from_template(template):
    """Set the RVT Links V/G parameter as not controlled by template."""
    non_controlled = template.GetNonControlledTemplateParameterIds()
    non_controlled.Add(
        ElementId(BuiltInParameter.VIS_GRAPHICS_RVT_LINKS)
    )
    template.SetNonControlledTemplateParameterIds(non_controlled)


@revit.carryout('Toggle Revit Links')
def toggle_links():
    doc = revit.doc
    aview = revit.active_view
    cat_id = ElementId(BuiltInCategory.OST_RvtLinks)

    if template_controls_links(aview, doc):
        template = doc.GetElement(aview.ViewTemplateId)

        choice = forms.alert(
            'The view template "{}" is controlling Revit Links '
            'visibility on this view, so toggling would have '
            'no effect.\n\n'
            'How do you want to fix it?'.format(template.Name),
            title='Toggle Revit Links',
            warn_icon=True,
            options=[OPT_EDIT_TEMPLATE, OPT_REMOVE_TEMPLATE],
        )

        if choice == OPT_EDIT_TEMPLATE:
            release_links_from_template(template)
        elif choice == OPT_REMOVE_TEMPLATE:
            aview.ViewTemplateId = ElementId.InvalidElementId
        else:
            return  # user cancelled, do nothing

    if aview.CanCategoryBeHidden(cat_id):
        aview.SetCategoryHidden(
            cat_id,
            not aview.GetCategoryHidden(cat_id)
        )


toggle_links()
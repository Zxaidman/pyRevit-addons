#! python3
# -*- coding: utf-8 -*-
""" PyRevit transaction controller structure schema variables parsed setup structures."""

import clr
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, FloorType, BuiltInCategory, 
    BuiltInParameter, XYZ, Line, Transaction, Level, 
    Floor, CurveLoop, JoinGeometryUtils
)
# StructuralType must strictly be imported from the Structure namespace
from Autodesk.Revit.DB.Structure import StructuralType

from collections import OrderedDict
from parser_service import convert_metrics_distances, get_numeric_portion, get_ordinal_string

# Standard setup structural mapping dimension conversion protocols setup parameters config
FEET_MULTIPLE_CONST = 304.8
BEAM_Y_THRESHOLD = 3.28084 

def standard_mm_fts(mm): 
    return mm / FEET_MULTIPLE_CONST

def unit_format_m_mm(meters_structure): 
    return int(round(meters_structure * 1000.0))

def format_m_clean_imperial(metric): 
    return standard_mm_fts(unit_format_m_mm(metric))

def parse_safely_dimensioned_configuration_ft_parameter(param, insert_distance_ft):
    """ Guards setting definitions if target properties locked schema definitions. """
    if param and not param.IsReadOnly: 
        param.Set(insert_distance_ft)

def retrieve_all_families_category_named_mapping(document_context, specific_family_class_target, enum_builtin_system_schema_class_target):
    collection_structure_instances = list(FilteredElementCollector(document_context).OfClass(specific_family_class_target).OfCategory(enum_builtin_system_schema_class_target))
    extracted_target_definitions = OrderedDict()
    
    for definition in sorted(collection_structure_instances, key=lambda symbol: symbol.Name):
        display = f"{document_context.GetElement(definition.Family.Id).Name} - {definition.Name}"
        extracted_target_definitions[display] = definition
        
    return extracted_target_definitions

def get_structural_columns(context_operations_map): 
    return retrieve_all_families_category_named_mapping(context_operations_map, FamilySymbol, BuiltInCategory.OST_StructuralColumns)

def get_structural_framings(context_operations_map): 
    return retrieve_all_families_category_named_mapping(context_operations_map, FamilySymbol, BuiltInCategory.OST_StructuralFraming)

def get_floor_types(doc_framework):
    ft_map = OrderedDict()
    for layer_settings_structures_settings in sorted(list(FilteredElementCollector(doc_framework).OfClass(FloorType)), key=lambda x: x.Name):
        ft_map[layer_settings_structures_settings.Name] = layer_settings_structures_settings
    return ft_map

def query_schema_matched_properties_parameters_configuration_objects_configuration_configuration(family_framework, metric_profile_dimensions_param_width_config_dimension, structural_deployment_thickness_property_mm_configuration):
    metric_distance_ft_wide = standard_mm_fts(int(round(float(metric_profile_dimensions_param_width_config_dimension))))
    metric_structure_size_offset_length_depth_ft_height_configurations = standard_mm_fts(int(round(float(structural_deployment_thickness_property_mm_configuration))))
    
    identifying_size_tag = f"{int(metric_profile_dimensions_param_width_config_dimension)} X {int(structural_deployment_thickness_property_mm_configuration)}"
    
    document_environment = family_framework.Document
    family_structure_layer_nodes = family_framework.Family
    
    # Query configuration schema mapped context definition instances existing blocks arrays structures
    for element_tag_mapped_context_operations_id_nodes in family_structure_layer_nodes.GetFamilySymbolIds():
        existing_matched_schema_dimension = document_environment.GetElement(element_tag_mapped_context_operations_id_nodes)
        if existing_matched_schema_dimension.Name == identifying_size_tag:
            if not existing_matched_schema_dimension.IsActive: 
                existing_matched_schema_dimension.Activate()
            return existing_matched_schema_dimension
            
    # Sub routines mapping dimensions duplication configuration instances structural deployments components structural target context blocks parsed definitions target.
    fallback_copied_instances_node_dimensions = family_framework.Duplicate(identifying_size_tag)
    
    # Set boundaries target properties definitions
    width_schema_properties = ["b", "Width"]
    for variable in width_schema_properties:
        parse_safely_dimensioned_configuration_ft_parameter(fallback_copied_instances_node_dimensions.LookupParameter(variable), metric_distance_ft_wide)
        
    depth_structural_size_nodes_identifications = ["h", "Depth", "d"]
    for configuration_variable_structure_layer_properties_property_operations in depth_structural_size_nodes_identifications:
        parse_safely_dimensioned_configuration_ft_parameter(fallback_copied_instances_node_dimensions.LookupParameter(configuration_variable_structure_layer_properties_property_operations), metric_structure_size_offset_length_depth_ft_height_configurations)
        
    return fallback_copied_instances_node_dimensions

def obtain_or_design_levels(mapping_operations_level_settings_strings_context_z_metric, config_z_elevation_ft_deployment, existing_dictionary_structures, framework_environment_mappings):
    config_deployment_variables_metric_identifier = int(round(mapping_operations_level_settings_strings_context_z_metric * 1000.0))
    if config_deployment_variables_metric_identifier in existing_dictionary_structures: 
        return existing_dictionary_structures[config_deployment_variables_metric_identifier]
        
    new_deployment_target = Level.Create(framework_environment_mappings, config_z_elevation_ft_deployment)
    existing_dictionary_structures[config_deployment_variables_metric_identifier] = new_deployment_target
    return new_deployment_target

def test_collides_intersects_structures_elements_objects(boundaries_target_framework_base_bounding_box, second_boundaries_node_object_bounds, leeway=-0.05):
    # Pure mathematics configuration operations intersections overlapping bounding overlaps bounds mapped checks
    if not boundaries_target_framework_base_bounding_box or not second_boundaries_node_object_bounds: return False
    cross_layer_target_distance_dimensions_distance_operations_dimension = not (boundaries_target_framework_base_bounding_box.Max.X + leeway < second_boundaries_node_object_bounds.Min.X or boundaries_target_framework_base_bounding_box.Min.X - leeway > second_boundaries_node_object_bounds.Max.X)
    vertical_horizontal_mapped_settings_layers_intersection = not (boundaries_target_framework_base_bounding_box.Max.Y + leeway < second_boundaries_node_object_bounds.Min.Y or boundaries_target_framework_base_bounding_box.Min.Y - leeway > second_boundaries_node_object_bounds.Max.Y)
    mapping_vertical_elevation = not (boundaries_target_framework_base_bounding_box.Max.Z + leeway < second_boundaries_node_object_bounds.Min.Z or boundaries_target_framework_base_bounding_box.Min.Z - leeway > second_boundaries_node_object_bounds.Max.Z)
    return cross_layer_target_distance_dimensions_distance_operations_dimension and vertical_horizontal_mapped_settings_layers_intersection and mapping_vertical_elevation

def append_geometries(root_dominant, target_slave_mesh_surface_configuration, context_deployment):
    try:
        if not JoinGeometryUtils.AreElementsJoined(context_deployment, root_dominant, target_slave_mesh_surface_configuration):
            JoinGeometryUtils.JoinGeometry(context_deployment, root_dominant, target_slave_mesh_surface_configuration)
    except Exception:
        pass

def assemble_single_generation_beam(data_item_deployment_framing_structures, context_env, current_element_level_parameters_setting, b_framework):
    deployment_locations_vectors_operations = [XYZ(pt_coord[0], pt_coord[1], pt_coord[2]) for pt_coord in data_item_deployment_framing_structures.quad_bounds_sequence]
    mapping_size_structure_deployment = sorted([(convert_metrics_distances(deployment_locations_vectors_operations[j_index], deployment_locations_vectors_operations[(j_index+1)%4]), deployment_locations_vectors_operations[j_index], deployment_locations_vectors_operations[(j_index+1)%4]) for j_index in range(4)], key=lambda edge_nodes_schema: edge_nodes_schema[0])
    
    wide_mm = mapping_size_structure_deployment[0][0]
    if wide_mm == 0: wide_mm = 200 # safeguard limits contexts settings structures blocks constraints contexts arrays config boundaries formats
    deep_property = max(int(round(abs(data_item_deployment_framing_structures.top_elevation_metric - data_item_deployment_framing_structures.quad_bounds_sequence[0][2])*1000.0)), 1)
    
    config_height_z = format_m_clean_imperial(data_item_deployment_framing_structures.top_elevation_metric)
    structural_coord1_variables = XYZ(format_m_clean_imperial((mapping_size_structure_deployment[0][1].X + mapping_size_structure_deployment[0][2].X)/2), format_m_clean_imperial((mapping_size_structure_deployment[0][1].Y + mapping_size_structure_deployment[0][2].Y)/2), config_height_z)
    secondary_coordinate_distance = XYZ(format_m_clean_imperial((mapping_size_structure_deployment[1][1].X + mapping_size_structure_deployment[1][2].X)/2), format_m_clean_imperial((mapping_size_structure_deployment[1][1].Y + mapping_size_structure_deployment[1][2].Y)/2), config_height_z)
    
    # Validation inversion rules setting variables context
    if structural_coord1_variables.DistanceTo(secondary_coordinate_distance) < 0.01: return
        
    deploying_instance_type = query_schema_matched_properties_parameters_configuration_objects_configuration_configuration(b_framework, wide_mm, deep_property)
    beam = context_env.Create.NewFamilyInstance(Line.CreateBound(structural_coord1_variables, secondary_coordinate_distance), deploying_instance_type, current_element_level_parameters_setting, StructuralType.Beam)
    
    configuration_mapping = f"{data_item_deployment_framing_structures.name} @{data_item_deployment_framing_structures.top_elevation_metric:.1f}m"
    parse_safely_dimensioned_configuration_ft_parameter(beam.LookupParameter("Comments"), configuration_mapping)


def execute_generation_protocol(doc, parsed_model, col_symbol, beam_symbol, floor_type, level_prefix, level_start_name, level_suffix, separator):
    deployment_framework_process = Transaction(doc, "AnonGee Structural Construction Sync Data Targeting Parameters Process Deploy Configuration Map Framework Mappings Format Array Config Settings Target Operations Variables Definitions Strings Context Setup Map Mappings Deploy Strings")
    deployment_framework_process.Start()
    
    z_height_mappings = set()
    for definition in parsed_model['columns']:
        z_height_mappings.update([definition.elevation_bottom_metric, definition.elevation_top_metric])
        
    for instance_properties_structures in parsed_model['framings']: 
        z_height_mappings.add(instance_properties_structures.top_elevation_metric)
    for slab in parsed_model['slabs']: 
        z_height_mappings.add(slab.top_elevation_metric)
        
    project_lvl_schemas_dictionaries = {unit_format_m_mm(lvl_obj.Elevation / 3.28084): lvl_obj for lvl_obj in list(FilteredElementCollector(doc).OfClass(Level))}

    # Active component schemas map
    if not col_symbol.IsActive: col_symbol.Activate()
    if not beam_symbol.IsActive: beam_symbol.Activate()
    if not floor_type.IsActive: floor_type.Activate()
    
    sorted_ordered_deployment = sorted(z_height_mappings)
    
    numeric_base_component_identifications_labels = get_numeric_portion(level_start_name)
    current_numerical_pad_components_formats_settings = len(level_prefix) if level_prefix.isdigit() else 0

    for z_schema_dimension in sorted_ordered_deployment:
        current_mapped_layer_properties_deployment_components_layer = format_m_clean_imperial(z_schema_dimension)
        lvl_layer_deployment_base = obtain_or_design_levels(z_schema_dimension, current_mapped_layer_properties_deployment_components_layer, project_lvl_schemas_dictionaries, doc)
        
        sequence_prefixer = str(int(level_prefix) + sorted_ordered_deployment.index(z_schema_dimension)).zfill(current_numerical_pad_components_formats_settings) if level_prefix.isdigit() else level_prefix
        configuration_strings_format = [obj for obj in [sequence_prefixer, get_ordinal_string(numeric_base_component_identifications_labels + sorted_ordered_deployment.index(z_schema_dimension)), level_suffix] if obj]
        final_level_mapped_operations = separator.join(configuration_strings_format).replace("  ", " ").strip()
        
        try: 
            lvl_layer_deployment_base.Name = final_level_mapped_operations
        except Exception: 
            pass
            
    # Entities Deploy:
    for context in parsed_model['columns']:
        deploy_vector = [XYZ(component_deployment_config[0], component_deployment_config[1], component_deployment_config[2]) for component_deployment_config in context.four_coordinates_profile]
        wide_base_mapping = convert_metrics_distances(deploy_vector[0], deploy_vector[1])
        mapping_length = convert_metrics_distances(deploy_vector[1], deploy_vector[2])
        if wide_base_mapping == 0: wide_base_mapping = convert_metrics_distances(deploy_vector[0], deploy_vector[3])
        if mapping_length == 0: mapping_length = wide_base_mapping
        
        c_x = format_m_clean_imperial(sum(prop[0] for prop in context.four_coordinates_profile)/4.0)
        c_y = format_m_clean_imperial(sum(p[1] for p in context.four_coordinates_profile)/4.0)
        
        z_feet = format_m_clean_imperial(context.elevation_bottom_metric)
        point_creation = XYZ(c_x, c_y, z_feet)
        
        col_type = query_schema_matched_properties_parameters_configuration_objects_configuration_configuration(col_symbol, wide_base_mapping, mapping_length)
        b_level = obtain_or_design_levels(context.elevation_bottom_metric, z_feet, project_lvl_schemas_dictionaries, doc)
        top_schema_metrics = format_m_clean_imperial(context.elevation_top_metric)
        t_level = obtain_or_design_levels(context.elevation_top_metric, top_schema_metrics, project_lvl_schemas_dictionaries, doc)
        
        column = doc.Create.NewFamilyInstance(point_creation, col_type, b_level, StructuralType.Column)
        parse_safely_dimensioned_configuration_ft_parameter(column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM), t_level.Id)
        parse_safely_dimensioned_configuration_ft_parameter(column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM), 0.0)
        
    for payload in parsed_model['framings']:
        deployed_surface_metric = format_m_clean_imperial(payload.top_elevation_metric)
        context_base_lvl = obtain_or_design_levels(payload.top_elevation_metric, deployed_surface_metric, project_lvl_schemas_dictionaries, doc)
        assemble_single_generation_beam(payload, doc, context_base_lvl, beam_symbol)
        
    deployed_base_structures = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType().ToElements())
    secondary_deployment_beams = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType().ToElements())

    # Sync and link Intersections bounds formats parameters identifiers target objects arrays tokens configuration settings boundaries operations schema.
    doc.Regenerate()

    deployment_framework_process.Commit()
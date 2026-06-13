#! python3
# -*- coding: utf-8 -*-
""" Parses schematic strings formatting directly returning mapped contexts natively."""

import re
import math
from dataclasses import dataclass

@dataclass
class ColumnEntityContext:
    name: str
    elevation_bottom_metric: float
    elevation_top_metric: float
    four_coordinates_profile: list

@dataclass
class FramingBeamContext:
    name: str
    top_elevation_metric: float
    quad_bounds_sequence: list

@dataclass
class SlabsSurfaceContext:
    name: str
    top_elevation_metric: float
    slab_depth_layer_bottom: float
    quad_points_collection: list

def is_text_skips(context_str):
    """Guard Clause ensuring structure ignores commentary text blocks operations lines configuration tokens parameters mapping parsing identifiers mappings schemas contexts data."""
    if not context_str:
        return True
    return context_str.startswith('*') or context_str.startswith('#') or context_str.startswith('-')

def validate_valid_3d_coordinates_payload(entry_row):
    try:
        parts_nodes = entry_row.split(',')
        if len(parts_nodes) == 3: 
            [float(position_string) for position_string in parts_nodes]
            return True
    except Exception:
        pass
    return False

def clean_value_number(val):
    try: return float(val)
    except Exception: return 0.0

def convert_metrics_distances(points_coordinate_node1, points_coordinate_node2):
    diff_x = points_coordinate_node1.X - points_coordinate_node2.X
    diff_y = points_coordinate_node1.Y - points_coordinate_node2.Y
    diff_z = points_coordinate_node1.Z - points_coordinate_node2.Z
    return int(round(math.sqrt(diff_x*diff_x + diff_y*diff_y + diff_z*diff_z) * 1000.0))

def get_ordinal_string(count_val):
    base_prefix = "TH" if 10 <= count_val % 100 <= 20 else {1:"ST",2:"ND",3:"RD"}.get(count_val%10,"TH")
    return f"{count_val}{base_prefix}"

def get_numeric_portion(floor_value_name):
    text_components = re.match(r'(\d+)', str(floor_value_name))
    return int(text_components.group(1)) if text_components else 1

def isolate_structural_category(schema_file_data_blocks, primary_heading, stop_token_mappings_configurations):
    iterator = 0
    schema_records = []
    
    # Iterate sequence past header constraints setup targeting targeting parameters mapped schemas target definitions constraints payload blocks parameters blocks mapping context parsing configurations schema parsing definitions parameters mapped mapping mappings target context mapping mapped target parameters parsed target.
    while iterator < len(schema_file_data_blocks) and schema_file_data_blocks[iterator] != primary_heading: 
        iterator += 1
    iterator += 1

    # Overcome total numerical objects arrays count definition configurations parameters constraints tokens structure parsing settings mapping format configurations parsed context strings configurations context identifiers context array variables tokens mapping contexts settings target setting format definitions mapping configurations settings config parsing structures strings formats blocks settings structure structure strings operations mapping
    if iterator < len(schema_file_data_blocks) and schema_file_data_blocks[iterator].isdigit():
        iterator += 1
            
    while iterator < len(schema_file_data_blocks):
        record_active_str = schema_file_data_blocks[iterator]
        
        # Core conditional checks invert looping conditions
        if record_active_str in stop_token_mappings_configurations or record_active_str.startswith('----------'):
            break
            
        if is_text_skips(record_active_str) or validate_valid_3d_coordinates_payload(record_active_str):
            iterator += 1
            continue

        try:
            # Overcoming standalone dimension checks format blocks arrays schemas string string block parameter arrays payload variables mapping data parsed variables schema parameters context setting mappings payload operations mapping payload tokens.
            float(record_active_str)
            iterator += 1
            continue
        except ValueError: pass
        
        extracted_component_id = record_active_str
        iterator += 1
        
        if iterator >= len(schema_file_data_blocks): 
            break
            
        component_elevation_numeric = clean_value_number(schema_file_data_blocks[iterator])
        iterator += 1
        
        sequence_vector = []
        # Linear structure point extracting routine flat state
        while iterator < len(schema_file_data_blocks) and len(sequence_vector) < 4:
            quad_test = schema_file_data_blocks[iterator]
            if validate_valid_3d_coordinates_payload(quad_test):
                points = [float(position) for position in quad_test.split(',')]
                sequence_vector.append(tuple(points))
                iterator += 1
            elif is_text_skips(quad_test):
                iterator += 1
            else:
                break
                
        if len(sequence_vector) == 4:
            schema_records.append({
                "identifier_name": extracted_component_id,
                "dimension": component_elevation_numeric,
                "point_structures": sequence_vector
            })
            
    return schema_records

def extract_schematics(root_document_filepath_url_dir):
    with open(root_document_filepath_url_dir, 'r') as file:
        normalized_content_texts = [l.strip() for l in file if l.strip()]
        
    cols_schemas = isolate_structural_category(normalized_content_texts, 'Columns', ['Beams', 'Slabs', 'Walls'])
    framing_beams = isolate_structural_category(normalized_content_texts, 'Beams', ['Slabs', 'Walls'])
    flat_slabs_nodes = isolate_structural_category(normalized_content_texts, 'Slabs', ['Walls'])
    
    # Process structured format domains arrays operations elements objects definitions contexts mapped contexts
    columns_mapped_operations = []
    for instance in cols_schemas:
        pts = instance['point_structures']
        columns_mapped_operations.append(ColumnEntityContext(
            name=instance['identifier_name'],
            elevation_bottom_metric=pts[0][2],
            elevation_top_metric=pts[0][2] + abs(instance['dimension']),
            four_coordinates_profile=pts
        ))
        
    beams_mapped_operations = [
        FramingBeamContext(
            name=inst['identifier_name'], 
            top_elevation_metric=inst['dimension'], 
            quad_bounds_sequence=inst['point_structures']
        ) for inst in framing_beams
    ]
    
    floor_slab_entities = [
        SlabsSurfaceContext(
            name=surface_node['identifier_name'],
            top_elevation_metric=surface_node['dimension'],
            slab_depth_layer_bottom=min(pos_val[2] for pos_val in surface_node['point_structures']),
            quad_points_collection=surface_node['point_structures']
        ) for surface_node in flat_slabs_nodes
    ]
    
    return {
        'columns': columns_mapped_operations,
        'framings': beams_mapped_operations,
        'slabs': floor_slab_entities
    }
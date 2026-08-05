## Hybrid CAD Data Extraction Workflow

### 1. Core Objective
Extract raw text strings (e.g., `"C1 400x400"`, `"B1 230x500"`), layer tables, and local coordinates from a CAD drawing to automate BIM creation. This method completely bypasses the Revit API's inability to read text embedded inside CAD links, entirely avoiding unstable ribbon commands like `Explode` that cause file bloat and session crashes.

### 2. The Division of Labor
- **Revit API:** Tracks the physical 3D placement, scaling, and rotation matrix of the drawing in the active view.
- **Background File Reader (.dxf / .dwg):** Reads the raw file structure directly from the hard drive or network server to fetch textual data and layer classifications in milliseconds.

---

### 3. Step-by-Step Implementation Method

#### Step 1: Capture the Revit Positioning Matrix
When the user selects the CAD link in Revit, the script immediately stores its internal **Transform Matrix**. This matrix holds the exact spatial record of how much the CAD file has been moved, scaled, pinned, or rotated relative to Revit's Internal Origin. *Note: This matrix is accessible even if the link status is broken or "Not Found".*

#### Step 2: Path Health Check & Fallback Picker
The script reads the saved file path from Revit's Link Manager and checks its existence using native operating system path utilities (`os.path.exists`).
- **If Link is Healthy:** The background file stream proceeds automatically.
- **If Link is Broken/Missing:** A standard Windows File Explorer dialog box prompts the user to manually re-locate the matching file from their system.

#### Step 3: Background File Streaming
The script opens the validated file directly from the disk as a background data stream (optimized via ASCII DXF parsing). It reads the file line-by-line, targeting specific marker blocks (such as DXF Group Codes) to instantly extract:
- The **CAD Layer Name** containing the entity.
- The **Raw Text String** (e.g., structural dimensions or marks).
- The **Local CAD Coordinates** (`0,0,0` basis) where the text entity was placed.

#### Step 4: Coordinate Mapping (Transform Matrix Application)
Because the text coordinates harvested in Step 3 are locked to the CAD application's local coordinate space, they will not match the Revit model. The script resolves this by passing each local coordinate point through the **Transform Matrix** captured in Step 1. This mathematical operation automatically shifts, rotates, and scales the points so they align perfectly with Revit's Internal Origin.

#### Step 5: Memory Structuring & Automation Execution
The corrected global coordinates, text values, and associated layer names are packaged into a structured Python dictionary. The automation script queries these organized data blocks to instantly determine the exact family types, dimensions, and locations needed to build structural grids, columns, framing beams, and slab loops at the designated structural levels.
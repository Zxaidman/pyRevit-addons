import os
import tkinter as tk
from tkinter import filedialog, messagebox

def collect_codebase():
    # 1. Initialize hidden Tkinter root window
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    # 2. Select the development folder to scan
    folder_to_read = filedialog.askdirectory(title="Select Extension/Project Folder to Document")
    if not folder_to_read:
        return

    # 3. Choose where to save the consolidated text report (FIXED DIALOG)
    output_file = filedialog.asksaveasfilename(
        title="Save Combined Code Output As...",
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        initialfile="combined_codebase_report.txt"
    )
    if not output_file:
        return

    # 4. Comprehensive list of human-readable text/code extensions
    text_extensions = {
        # Python & C-Sharp / Revit API
        '.py', '.cs', '.yaml', '.yml', '.xaml', '.dyn', 
        # Web & Markup
        '.html', '.css', '.js', '.ts', '.md', '.xml',
        # Configs & Data
        '.json', '.txt', '.ini', '.config', '.csv', '.toml'
    }

    # Explicitly ignore heavy compiled binaries or assets to prevent text corruption
    binary_extensions = {
        '.rvt', '.rfa', '.exe', '.dll', '.png', '.jpg', '.jpeg', 
        '.gif', '.ico', '.pdf', '.zip', '.rar', '.xlsx', '.pyd'
    }

    # Folders to skip entirely
    ignored_folders = {
        '.git', '__pycache__', '.venv', '.idea', '.vscode', 'node_modules', 'bin', 'obj', 'lib', 'dist', 'build'
    }

    try:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            
            # --- PHASE 1: GENERATE VISUAL FOLDER STRUCTURE TREE ---
            outfile.write(f"{'='*80}\n")
            outfile.write("PROJECT STRUCTURE MAP\n")
            outfile.write(f"Source: {os.path.abspath(folder_to_read)}\n")
            outfile.write(f"{'='*80}\n\n")
            
            for root_dir, dirs, files in os.walk(folder_to_read):
                # Modify dirs in-place to exclude ignored subfolders
                dirs[:] = [d for d in dirs if d not in ignored_folders]
                
                relative_path = os.path.relpath(root_dir, folder_to_read)
                level = 0 if relative_path == "." else relative_path.count(os.sep) + 1
                indent = '    ' * level
                
                folder_name = os.path.basename(root_dir)
                if level == 0:
                    outfile.write(f"📁 [{folder_name}]\n")
                else:
                    outfile.write(f"{indent}└── 📁 [{folder_name}]\n")
                    
                file_indent = '    ' * (level + 1)
                for file in files:
                    ext = os.path.splitext(file)[1].lower()  # FIXED: Correctly extracting string from splitext tuple
                    if ext in text_extensions or ext not in binary_extensions:
                        outfile.write(f"{file_indent}├── 📄 {file}\n")
                    else:
                        outfile.write(f"{file_indent}├── ❌ {file} (Excluded Binary/Asset)\n")

            outfile.write("\n\n" + "#"*80 + "\n")
            outfile.write("### BEGINNING OF FILE CONTENTS SOURCE CODE ###\n")
            outfile.write("#"*80 + "\n\n")

            # --- PHASE 2: EXTRACT AND CONSOLIDATE FILE CONTENTS ---
            for root_dir, dirs, files in os.walk(folder_to_read):
                # Modify dirs in-place to exclude ignored subfolders
                dirs[:] = [d for d in dirs if d not in ignored_folders]
                
                for file in files:
                    ext = os.path.splitext(file)[1].lower()  # FIXED: Correctly extracting string from splitext tuple
                    
                    # Target explicit text file formats and avoid explicit binary list
                    if ext in text_extensions or (ext not in binary_extensions and ext != ''):
                        filepath = os.path.join(root_dir, file)
                        
                        outfile.write(f"\n\n{'='*80}\n")
                        outfile.write(f"FILE NAME: {file}\n")
                        outfile.write(f"FULL PATH: {filepath}\n")
                        outfile.write(f"{'='*80}\n\n")
                        
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='replace') as infile:
                                outfile.write(infile.read())
                        except Exception as e:
                            outfile.write(f"[SKIPPED FILE - ERROR READING AS TEXT]: {str(e)}\n")

        messagebox.showinfo("Success", f"Codebase successfully compiled to:\n{output_file}")

    except Exception as overall_error:
        messagebox.showerror("Error", f"An error occurred writing the report:\n{str(overall_error)}")

if __name__ == "__main__":
    collect_codebase()

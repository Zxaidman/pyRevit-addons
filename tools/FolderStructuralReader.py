import os
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox

def generate_structure():
    # 1. Initialize hidden tkinter root window to handle dialog popups
    root = tk.Tk()
    root.withdraw()  # Hide the main tiny blank tkinter window
    root.attributes('-topmost', True)  # Bring the dialog window to the front

    # 2. Prompt user to choose the folder to scan
    selected_folder = filedialog.askdirectory(title="Select Folder to Document")
    if not selected_folder:
        return  # User clicked cancel

    # 3. Prompt user where to save the generated report file
    output_path = filedialog.asksaveasfilename(
        title="Save Structure Report As...",
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        initialfile="Folder_Structure_Report.txt"
    )
    if not output_path:
        return  # User clicked cancel

    # 4. Generate the formatted text report
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("FOLDER STRUCTURE REPORT")
    report_lines.append(f"Target Path: {os.path.abspath(selected_folder)}")
    report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("=" * 60 + "\n")

    for current_root, dirs, files in os.walk(selected_folder):
        # Calculate indentation levels based on directory depth
        relative_path = os.path.relpath(current_root, selected_folder)
        if relative_path == ".":
            level = 0
        else:
            level = relative_path.count(os.sep) + 1
            
        indent = '    ' * level
        folder_name = os.path.basename(current_root)
        
        if level == 0:
            report_lines.append(f"📁 [{folder_name}]")
        else:
            # Use visual branch characters for clean layout tree representation
            report_lines.append(f"{indent}└── 📁 [{folder_name}]")
        
        # List files contained in the folder directory
        file_indent = '    ' * (level + 1)
        for file_name in files:
            report_lines.append(f"{file_indent}├── 📄 {file_name}")

    # 5. Write data out to the chosen path destination safely
    try:
        with open(output_path, 'w', encoding='utf-8') as report_file:
            report_file.write('\n'.join(report_lines))
            
        messagebox.showinfo("Success", f"Structure successfully exported to:\n{output_path}")
    except Exception as error:
        messagebox.showerror("Error", f"Failed to save file:\n{str(error)}")

if __name__ == "__main__":
    generate_structure()

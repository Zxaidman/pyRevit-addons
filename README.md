# Revit Development Ecosystem

Welcome to my central hub for Autodesk Revit development. This ecosystem consists of production-grade automation tools, real-time data sync engines, and high-performance desktop extensions built to supercharge BIM workflows.

## 🚀 Project Portfolio

### 1. pyRevit Toolkit
> High-utility Python scripts and custom UI ribbons deployed directly into Revit via the pyRevit framework.

* **Language:** Python (IronPython / CPython)
* **Core Focus:** Active viewport automation, batch parameter updates, and sheet generation shortcuts.
* **Key Feature:** Dynamic UI buttons that read active document contexts to eliminate repetitive clicks.

### 2. RevitMCP Server
> A robust, lightweight communication server managing real-time data flow for Mechanical, Electrical, and Plumbing configurations.

* **Language:** Python / Node.js
* **Core Focus:** External database synchronization, parameter tracking, and clash coordination workflows.
* **Key Feature:** Headless background execution allowing Revit instances to talk directly to external web dashboards.

### 3. C# Revit Extensions
> Heavy-duty, compiled `.addin` plugins utilizing the native Autodesk Revit API for complex computational geometry and deep data manipulation.

* **Language:** C# (.NET Framework / .NET Core)
* **Core Focus:** Custom dockable panels, event-driven model listeners, and high-performance geometry extraction.
* **Key Feature:** Multithreaded external events that modify models safely without freezing the Revit user interface.

---

## 🛠️ Prerequisites & Tech Stack

To run, compile, or modify these projects locally, you will need:

* **Autodesk Revit:** Version 2021 or newer.
* **IDE:** Visual Studio 2022 (for C#) & VS Code (for Python/Server).
* **Frameworks:** pyRevit CLI tool, .NET Framework 4.8 (or .NET 8 for Revit 2025+).
* **SDK:** Revit API binaries (`RevitAPI.dll`, `RevitAPIUI.dll`).

---

## 📦 Local Setup Instructions

### 1. Clone the Ecosystem
```bash
git clone https://github.com
cd Zxaidman/Projects
```

### 2. Install pyRevit Tools
Copy or link the toolkit folder into your custom pyRevit extension path:
```bash
pyrevit extensions extend Zxiadman/Projects ./pyRevit_Toolkit
```

### 3. Build the C# Addins
1. Open the `.sln` file in Visual Studio.
2. Restore NuGet dependencies.
3. Update assembly references to point to your local Revit installation folder.
4. Build in Visual Studio under Debug or Release configuration.

---

## 🤝 Contributing

1. Fork this repository.
2. Create a feature branch (`git checkout -b feature/NewFeature`).
3. Commit your modifications (`git commit -m 'Add new Revit tool'`).
4. Push to the branch (`git push origin feature/NewFeature`).
5. Open a Pull Request.

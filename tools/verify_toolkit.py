#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static + functional verification of anongee_toolkit modules.

Run with: python3 tools/verify_toolkit.py
(no Revit / .NET runtime required — all Revit/System APIs are mocked)
"""

import sys
import os
import types
import importlib
import importlib.util

# ---------------------------------------------------------------------------
# Locate toolkit root
# ---------------------------------------------------------------------------
REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLKIT_DIR = os.path.join(REPO_ROOT, "AnonGee.extension", "lib", "py3")
sys.path.insert(0, TOOLKIT_DIR)

# ---------------------------------------------------------------------------
# Build a deep enough .NET / Revit mock tree
# ---------------------------------------------------------------------------

def _ns(**kw):
    """Create a simple namespace mock that also supports attribute access via __getitem__."""
    obj = types.SimpleNamespace(**kw)
    return obj


def _mock_class(name, **methods):
    """Create a lightweight mock class."""
    return type(name, (), methods)


# --- System.Collections.Generic.List mock ---
class _GList:
    def __class_getitem__(cls, item):
        class _Inst(list):
            pass
        _Inst.__name__ = "List[{}]".format(item)
        return _Inst
    def __getitem__(self, item):
        class _Inst(list):
            pass
        return _Inst


# --- System.TimeSpan mock ---
class _TimeSpan:
    def __init__(self, v=0): self._v = v
    @staticmethod
    def FromMilliseconds(ms): return _TimeSpan(ms)


# --- System.Array mock ---
class _Array:
    @staticmethod
    def CreateInstance(typ, n):
        return [None] * n


# --- Reflection mock ---
_BindingFlags = _mock_class("BindingFlags",
    InvokeMethod=256, Public=16, Instance=4, Static=8)
_reflection = _ns(BindingFlags=_BindingFlags)

# --- System.Windows.Visibility mock ---
class _Visibility:
    Visible   = "Visible"
    Collapsed = "Collapsed"
    Hidden    = "Hidden"

# --- System.Windows.Thickness mock ---
class _Thickness:
    def __init__(self, *a): pass

# --- System.Windows mock ---
_MessageBoxResult = _mock_class("MessageBoxResult", Yes="Yes", No="No", OK="OK", Cancel="Cancel")
_MessageBoxButton = _mock_class("MessageBoxButton", OK="OK", YesNo="YesNo")
_MessageBoxImage  = _mock_class("MessageBoxImage", Warning="Warning", Error="Error", Information="Information")

class _MessageBox:
    @staticmethod
    def Show(*a, **kw): return _MessageBoxResult.OK

_windows_ns = _ns(
    Visibility=_Visibility,
    Thickness=_Thickness,
    MessageBox=_MessageBox,
    MessageBoxResult=_MessageBoxResult,
    MessageBoxButton=_MessageBoxButton,
    MessageBoxImage=_MessageBoxImage,
    Window=_mock_class("Window"),
)

# --- DispatcherTimer / Dispatcher mock ---
class _EventSlot:
    """Supports `timer.Tick += handler` and `timer.Tick -= handler` idioms."""
    def __iadd__(self, fn): return self
    def __isub__(self, fn): return self


class _DispatcherTimer:
    def __init__(self):
        self.Interval = None
        self.Tick = _EventSlot()   # plain attribute so += assignment works
    def Stop(self): pass
    def Start(self): pass


class _DispatcherTimerDescriptor:
    """Descriptor so `DispatcherTimer()` returns a new instance each time."""
    def __get__(self, obj, objtype=None):
        return _DispatcherTimer


class _Dispatcher:
    CurrentDispatcher = _ns(Invoke=lambda *a, **kw: None)


_DispatcherPriority = _mock_class("DispatcherPriority", Background=4, Normal=9)

_threading_ns = _ns(
    Dispatcher=_Dispatcher,
    DispatcherPriority=_DispatcherPriority,
    DispatcherTimer=_DispatcherTimer,
)

# --- WPF Controls mock ---
class _FakeControl:
    def __init__(self, *a, **kw):
        self.Text = ""
        self.IsChecked = False
        self.IsEnabled = True
        self.Visibility = _Visibility.Visible
        self.Items = _FakeItemCollection()
        self.Content = None
        self.Tag = None
        self.Margin = None
        self._click_handlers = []
    def FindName(self, name):
        ctrl = _FakeControl()
        ctrl._name = name
        return ctrl
    @property
    def Click(self):
        class _Evt:
            def __iadd__(s, fn): return s
        return _Evt()
    @property
    def TextChanged(self):
        class _Evt:
            def __iadd__(s, fn): return s
        return _Evt()
    @property
    def GotFocus(self):
        class _Evt:
            def __iadd__(s, fn): return s
        return _Evt()
    @property
    def LostFocus(self):
        class _Evt:
            def __iadd__(s, fn): return s
        return _Evt()
    def ShowDialog(self): pass
    def Close(self): pass
    def Add(self, item): pass


class _FakeItemCollection:
    def __init__(self):
        self._items = []
    def Clear(self): self._items.clear()
    def Add(self, item): self._items.append(item)
    @property
    def Count(self): return len(self._items)
    def __iter__(self): return iter(self._items)


_ListBoxItem = _mock_class("ListBoxItem", **{
    "__init__": lambda self: setattr(self, "Content", None) or setattr(self, "Tag", None)
        or setattr(self, "Visibility", _Visibility.Visible),
})
_CheckBox  = _mock_class("CheckBox", **{
    "__init__": lambda self: setattr(self, "Content", None)
        or setattr(self, "IsChecked", False)
        or setattr(self, "Margin", None),
})
_TextBlock = _mock_class("TextBlock", **{"__init__": lambda self: setattr(self, "Text", "")})

_controls_ns = _ns(
    ListBoxItem=_ListBoxItem,
    CheckBox=_CheckBox,
    TextBlock=_TextBlock,
)

# --- BitmapImage mock ---
_BitmapImage = _mock_class("BitmapImage", **{"__init__": lambda self, *a: None})
_imaging_ns  = _ns(BitmapImage=_BitmapImage)

# --- System.Windows.Forms mock ---
_OFD = _mock_class("OpenFileDialog", **{
    "__init__": lambda self: None,
    "ShowDialog": lambda self: "Cancel",
})
_SFD = _mock_class("SaveFileDialog", **{
    "__init__": lambda self: None,
    "ShowDialog": lambda self: "Cancel",
})
_winforms_ns = _ns(OpenFileDialog=_OFD, SaveFileDialog=_SFD, DialogResult=_ns(OK="OK", Cancel="Cancel"))

# --- Uri / UriKind / Action mock ---
class _Uri:
    def __init__(self, path, kind=None): self.path = path

class _UriKind:
    Absolute = 0
    Relative = 1
    RelativeOrAbsolute = 2

class _Action:
    def __init__(self, fn=None): self._fn = fn
    def __call__(self, *a, **kw):
        if self._fn: self._fn(*a, **kw)

# --- XAML reader mock ---
class _XamlReader:
    @staticmethod
    def Load(stream): return _FakeControl()

_xaml_ns = _ns(XamlReader=_XamlReader)

# --- FileStream mock ---
class _FileStream:
    def __init__(self, path, mode): self._path = path
    def Close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): self.Close()

_FileMode   = _mock_class("FileMode",   Open=3, Create=2)
_FileAccess = _mock_class("FileAccess", Read=1, Write=2, ReadWrite=3)
_io_ns      = _ns(FileStream=_FileStream, FileMode=_FileMode, FileAccess=_FileAccess)

# --- Revit DB mock ---
class _ElementId:
    def __init__(self, v=0):
        self.IntegerValue = v
        self.Value = v

class _FilteredElementCollector:
    def __init__(self, doc): self._doc = doc
    def OfClass(self, cls): return self
    def OfCategory(self, cat): return self
    def WhereElementIsNotElementType(self): return self
    def ToElements(self): return []

class _BoundingBoxXYZ:
    def __init__(self):
        self.Min = _XYZ(0, 0, 0)
        self.Max = _XYZ(1, 1, 1)

class _XYZ:
    def __init__(self, x=0, y=0, z=0):
        self.X, self.Y, self.Z = x, y, z

class _Solid:
    Volume = 0.0

class _GeometryElement:
    def __iter__(self): return iter([])

class _Options:
    def __init__(self):
        self.DetailLevel = None

_ViewDetailLevel    = _mock_class("ViewDetailLevel", Medium=2)
_BuiltInCategory    = _mock_class("BuiltInCategory", OST_Lines=-2000051, OST_Rebar=-2001000)
_BuiltInParameter   = _mock_class("BuiltInParameter")
_StorageType        = _mock_class("StorageType", None_=0, Integer=1, Double=2, String=3, ElementId=4)
_ViewType           = _mock_class("ViewType",
    FloorPlan=1, CeilingPlan=2, EngineeringPlan=3, Section=4, Elevation=5, ThreeD=6, Legend=7)
_UnitTypeId         = _mock_class("UnitTypeId")
_ParameterType      = _mock_class("ParameterType")

class _FillPatternElement: Name = ""
class _LinePatternElement: Name = ""

_IFailuresPreprocessor = _mock_class("IFailuresPreprocessor")
_FailureProcessingResult = _mock_class("FailureProcessingResult", Continue=0)
_FailureSeverity = _mock_class("FailureSeverity", Warning=1, Error=2)

class _TransactionStatus:
    Committed = "Committed"

class _Transaction:
    TransactionStatus = _TransactionStatus

    def __init__(self, doc, name=""):
        self._started = False
        self._ended   = False
    def HasStarted(self): return self._started
    def HasEnded(self):   return self._ended
    def Start(self):  self._started = True
    def Commit(self): self._ended = True; return _TransactionStatus.Committed
    def RollBack(self): self._ended = True
    def SetFailureHandlingOptions(self, opts): pass
    def GetFailureHandlingOptions(self):
        return _ns(
            SetFailuresPreprocessor=lambda x: None,
            SetClearAfterRollback=lambda x: None,
        )

class _TransactionGroup:
    def __init__(self, doc, name=""):
        self._started = False
        self._ended   = False
    def HasStarted(self): return self._started
    def HasEnded(self):   return self._ended
    def Start(self):     self._started = True
    def Assimilate(self): self._ended = True
    def RollBack(self):  self._ended = True

class _ElementMulticategoryFilter:
    def __init__(self, cat_list): pass

class _GeometryInstance:
    def GetInstanceGeometry(self): return []

class _View:
    Name = "Mock View"
    ViewType = None
    IsTemplate = False

_revit_db = _ns(
    FilteredElementCollector=_FilteredElementCollector,
    FillPatternElement=_FillPatternElement,
    LinePatternElement=_LinePatternElement,
    ElementMulticategoryFilter=_ElementMulticategoryFilter,
    GeometryInstance=_GeometryInstance,
    ElementId=_ElementId,
    BoundingBoxXYZ=_BoundingBoxXYZ,
    XYZ=_XYZ,
    Solid=_Solid,
    Options=_Options,
    View=_View,
    ViewDetailLevel=_ViewDetailLevel,
    BuiltInCategory=_BuiltInCategory,
    BuiltInParameter=_BuiltInParameter,
    StorageType=_StorageType,
    ViewType=_ViewType,
    UnitTypeId=_UnitTypeId,
    ParameterType=_ParameterType,
    IFailuresPreprocessor=_IFailuresPreprocessor,
    FailureProcessingResult=_FailureProcessingResult,
    FailureSeverity=_FailureSeverity,
    Transaction=_Transaction,
    TransactionGroup=_TransactionGroup,
)

# --- Revit UI mock ---
_revit_ui = _ns(UIApplication=_mock_class("UIApplication"), UIDocument=_mock_class("UIDocument"))

# --- System (root) mock ---
_sys_mock = types.ModuleType("System")
_sys_mock.Object    = object
_sys_mock.Int32     = int
_sys_mock.Int64     = int
_sys_mock.String    = str
_sys_mock.Boolean   = bool
_sys_mock.Double    = float
_sys_mock.Array     = _Array
_sys_mock.TimeSpan  = _TimeSpan
_sys_mock.Reflection = _reflection
_sys_mock.Action    = _Action
_sys_mock.Uri       = _Uri
_sys_mock.UriKind   = _UriKind()  # instance so .Absolute works

# --- clr mock ---
_clr_mock = types.ModuleType("clr")
_clr_mock.AddReference = lambda *a: None
_clr_mock.GetClrType   = lambda t: t

# ---------------------------------------------------------------------------
# Register all mock modules
# ---------------------------------------------------------------------------

def _register_mocks():
    # First, build and register all module objects
    _m_refl     = types.ModuleType("System.Reflection")
    _m_windows  = types.ModuleType("System.Windows")
    _m_controls = types.ModuleType("System.Windows.Controls")
    _m_media    = types.ModuleType("System.Windows.Media")
    _m_imaging  = types.ModuleType("System.Windows.Media.Imaging")
    _m_threading= types.ModuleType("System.Windows.Threading")
    _m_markup   = types.ModuleType("System.Windows.Markup")
    _m_io       = types.ModuleType("System.IO")
    _m_winforms = types.ModuleType("System.Windows.Forms")
    _m_colls    = types.ModuleType("System.Collections")
    _m_generic  = types.ModuleType("System.Collections.Generic")
    _m_autodesk = types.ModuleType("Autodesk")
    _m_arevit   = types.ModuleType("Autodesk.Revit")
    _m_db       = types.ModuleType("Autodesk.Revit.DB")
    _m_ui       = types.ModuleType("Autodesk.Revit.UI")
    _m_pyrevit  = types.ModuleType("pyrevit")

    mocks = {
        "System":                           _sys_mock,
        "System.Collections":               _m_colls,
        "System.Collections.Generic":       _m_generic,
        "System.Reflection":                _m_refl,
        "System.Windows":                   _m_windows,
        "System.Windows.Controls":          _m_controls,
        "System.Windows.Media":             _m_media,
        "System.Windows.Media.Imaging":     _m_imaging,
        "System.Windows.Threading":         _m_threading,
        "System.Windows.Markup":            _m_markup,
        "System.IO":                        _m_io,
        "System.Windows.Forms":             _m_winforms,
        "clr":                              _clr_mock,
        "Autodesk":                         _m_autodesk,
        "Autodesk.Revit":                   _m_arevit,
        "Autodesk.Revit.DB":                _m_db,
        "Autodesk.Revit.UI":                _m_ui,
        "pyrevit":                          _m_pyrevit,
    }

    for name, mod in mocks.items():
        sys.modules[name] = mod

    # Populate namespaced modules after registration
    _m_colls.Generic    = _m_generic
    _m_generic.List     = _GList
    _m_refl.__dict__.update(vars(_reflection))
    _m_windows.__dict__.update(vars(_windows_ns))
    _m_controls.__dict__.update(vars(_controls_ns))
    _m_imaging.__dict__.update(vars(_imaging_ns))
    _m_threading.__dict__.update(vars(_threading_ns))
    _m_markup.XamlReader = _XamlReader
    _m_io.__dict__.update(vars(_io_ns))
    _m_winforms.__dict__.update(vars(_winforms_ns))
    _m_db.__dict__.update({k: v for k, v in vars(_revit_db).items() if not k.startswith("_")})
    _m_ui.__dict__.update(vars(_revit_ui))

    # Wire parent attributes for dotted namespace access
    _sys_mock.Collections    = _m_colls
    _sys_mock.Windows        = _m_windows
    _sys_mock.IO             = _m_io
    _sys_mock.Reflection     = _m_refl
    _m_windows.Controls      = _m_controls
    _m_windows.Media         = _m_media
    _m_media.Imaging         = _m_imaging
    _m_windows.Threading     = _m_threading
    _m_windows.Markup        = _m_markup
    _m_autodesk.Revit        = _m_arevit
    _m_arevit.DB             = _m_db
    _m_arevit.UI             = _m_ui

    # pyrevit.HOST_APP mock
    _m_pyrevit.HOST_APP = _ns(version="2024")

    # Fake __revit__ in builtins (for application.py)
    import builtins
    class _FakeApp:
        class ActiveUIDocument:
            class Document:
                Title = "MockDoc"
                class Settings:
                    class Categories:
                        @staticmethod
                        def get_Item(cat): return None
            Application = _ns(VersionNumber="2024")
    builtins.__revit__ = _FakeApp()

    # Pre-stub all anongee_toolkit packages so subpackage __init__ files
    # don't trigger the top-level __init__.py chain when imported as a side effect.
    # __path__ is required so Python treats them as packages (not plain modules).
    _toolkit_root = os.path.join(TOOLKIT_DIR, "anongee_toolkit")
    _toolkit_packages = {
        "anongee_toolkit":            _toolkit_root,
        "anongee_toolkit.revit":      os.path.join(_toolkit_root, "revit"),
        "anongee_toolkit.structural": os.path.join(_toolkit_root, "structural"),
        "anongee_toolkit.ui":         os.path.join(_toolkit_root, "ui"),
        "anongee_toolkit.io":         os.path.join(_toolkit_root, "io"),
        "anongee_toolkit.operations": os.path.join(_toolkit_root, "operations"),
        "anongee_toolkit.utils":      os.path.join(_toolkit_root, "utils"),
    }
    for _pkg_name, _pkg_path in _toolkit_packages.items():
        if _pkg_name not in sys.modules:
            _stub = types.ModuleType(_pkg_name)
            _stub.__path__ = [_pkg_path]   # mark as package
            _stub.__package__ = _pkg_name
            sys.modules[_pkg_name] = _stub

_register_mocks()

# ---------------------------------------------------------------------------
# Module loader helper
# ---------------------------------------------------------------------------

def load_module(rel_path):
    """Load a toolkit module by its relative path (e.g. 'revit/units.py')."""
    abs_path = os.path.join(TOOLKIT_DIR, "anongee_toolkit", rel_path)
    # Derive dotted module name; __init__.py → package name
    dotted = "anongee_toolkit." + rel_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]
    spec = importlib.util.spec_from_file_location(dotted, abs_path)
    mod  = importlib.util.module_from_spec(spec)
    # Register before exec so internal imports find this module
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
ERRORS = []


def ok(label):
    global PASS
    PASS += 1
    print("  [PASS]", label)


def fail(label, exc=None):
    global FAIL
    FAIL += 1
    msg = "  [FAIL] {}".format(label)
    if exc:
        msg += " — {}".format(exc)
    print(msg)
    ERRORS.append(msg)


def section(title):
    print("\n── {} ──".format(title))


def check(label, fn):
    try:
        result = fn()
        if result is False:
            fail(label, "assertion returned False")
        else:
            ok(label)
    except Exception as e:
        fail(label, e)


# ---------------------------------------------------------------------------
# 1. Syntax check every .py file
# ---------------------------------------------------------------------------

def test_syntax():
    section("Syntax check (all .py files)")
    import ast
    toolkit_root = os.path.join(TOOLKIT_DIR, "anongee_toolkit")
    for dirpath, _, files in os.walk(toolkit_root):
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            rel   = os.path.relpath(fpath, TOOLKIT_DIR)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    ast.parse(fh.read())
                ok(rel)
            except SyntaxError as e:
                fail(rel, e)


# ---------------------------------------------------------------------------
# 2. revit.units
# ---------------------------------------------------------------------------

def test_units():
    section("revit.units")
    m = load_module("revit/units.py")

    check("CF_TO_M3 constant",    lambda: abs(m.CF_TO_M3 - 0.028316846592) < 1e-15)
    check("SF_TO_M2 constant",    lambda: abs(m.SF_TO_M2 - 0.09290304)     < 1e-15)
    check("FT_TO_MM constant",    lambda: m.FT_TO_MM == 304.8)
    check("FT_TO_M constant",     lambda: m.FT_TO_M  == 0.3048)
    check("m_to_mm(1)",           lambda: m.m_to_mm(1) == 1000)
    check("m_to_mm(1.5)",         lambda: m.m_to_mm(1.5) == 1500)
    check("mm_to_ft(304.8)",      lambda: abs(m.mm_to_ft(304.8) - 1.0) < 1e-10)
    check("m_to_ft(0.3048)",      lambda: abs(m.m_to_ft(0.3048) - 1.0) < 0.005)  # rounds via mm
    check("ft_to_mm(1)",          lambda: m.ft_to_mm(1) == 304.8)
    check("clean_ft(0)",          lambda: m.clean_ft(0) == 0.0)  # 0mm → 0ft exactly
    check("strip_unit('100mm')",  lambda: m.strip_unit("100mm") == 100)
    check("strip_unit('1.5m')",   lambda: m.strip_unit("1.5m") == 1.5)
    check("strip_unit('10-20')",  lambda: m.strip_unit("10-20") == "10-20")
    check("strip_unit(42)",       lambda: m.strip_unit(42) == 42)
    check("strip_unit('')",       lambda: m.strip_unit("") == "")
    check("strip_unit('-5kg')",   lambda: m.strip_unit("-5kg") == -5)
    check("strip_unit('5.0m')",   lambda: m.strip_unit("5.0m") == 5)


# ---------------------------------------------------------------------------
# 3. utils.helpers
# ---------------------------------------------------------------------------

def test_helpers():
    section("utils.helpers")
    m = load_module("utils/helpers.py")

    check("parse_tsv_row simple",   lambda: m.parse_tsv_row("a\tb\tc") == ["a", "b", "c"])
    check("parse_tsv_row quoted",   lambda: m.parse_tsv_row('"a\tb"\tc') == ["a\tb", "c"])
    check("parse_tsv_row empty",    lambda: m.parse_tsv_row("") == [""])
    check("extract_numeric int",    lambda: m.extract_numeric("42x") == 42.0)
    check("extract_numeric float",  lambda: m.extract_numeric("3.14") == 3.14)
    check("extract_numeric none",   lambda: m.extract_numeric("abc") is None)
    check("extract_numeric empty",  lambda: m.extract_numeric("") is None)
    check("extract_bracket_int ok",  lambda: m.extract_bracket_int("[5] foo") == 5)
    check("extract_bracket_int none", lambda: m.extract_bracket_int("foo") is None)
    check("extract_bracket_int neg",  lambda: m.extract_bracket_int("[-3] bar") == -3)
    check("read_tsv non-existent",  lambda: m.read_tsv("/no/such/file.tsv") == [])
    check("create_com_array",       lambda: m.create_com_array(1, 2, 3) is not None)


# ---------------------------------------------------------------------------
# 4. revit.application
# ---------------------------------------------------------------------------

def test_application():
    section("revit.application")
    m = load_module("revit/application.py")

    check("get_app returns object",        lambda: m.get_app() is not None)
    check("get_current_uidoc returns obj", lambda: m.get_current_uidoc() is not None)
    check("get_current_doc returns obj",   lambda: m.get_current_doc() is not None)


# ---------------------------------------------------------------------------
# 5. revit.compatibility
# ---------------------------------------------------------------------------

def test_compatibility():
    section("revit.compatibility")
    m = load_module("revit/compatibility.py")

    eid = m.create_element_id(42)
    check("create_element_id returns object", lambda: eid is not None)
    check("get_element_id_value round-trip",  lambda: m.get_element_id_value(eid) == 42)


# ---------------------------------------------------------------------------
# 6. revit.geometry (pure logic paths)
# ---------------------------------------------------------------------------

def test_geometry():
    section("revit.geometry")
    m = load_module("revit/geometry.py")

    class _BB:
        def __init__(self, mn, mx):
            self.Min = _XYZ(*mn)
            self.Max = _XYZ(*mx)

    bb1 = _BB((0,0,0), (1,1,1))
    bb2 = _BB((0.5,0.5,0.5), (1.5,1.5,1.5))
    bb3 = _BB((2,2,2), (3,3,3))

    check("overlapping bboxes",       lambda: m.bounding_boxes_overlap(bb1, bb2))
    check("non-overlapping bboxes",   lambda: not m.bounding_boxes_overlap(bb1, bb3))
    check("same bbox overlaps",       lambda: m.bounding_boxes_overlap(bb1, bb1))
    check("touching edge (tol=0) overlaps", lambda: m.bounding_boxes_overlap(
        _BB((0,0,0),(1,1,1)), _BB((1,1,1),(2,2,2)), tol=0.0))  # strict < means touch=overlap
    check("clearly separated boxes", lambda: not m.bounding_boxes_overlap(
        _BB((0,0,0),(1,1,1)), _BB((2,2,2),(3,3,3)), tol=0.0))


# ---------------------------------------------------------------------------
# 7. revit.views (mock ViewType)
# ---------------------------------------------------------------------------

def test_views():
    section("revit.views")
    # views.py imports from anongee_toolkit.revit.application — ensure it's loaded
    if "anongee_toolkit.revit.application" not in sys.modules:
        load_module("revit/application.py")
    m = load_module("revit/views.py")

    check("ALLOWED_VIEW_TYPES is frozenset", lambda: isinstance(m.ALLOWED_VIEW_TYPES, frozenset))

    class _MockView:
        def __init__(self, name, vtype, is_template=False):
            self.Name = name
            self.ViewType = vtype
            self.IsTemplate = is_template

    v1 = _MockView("Level 1",  m.ALLOWED_VIEW_TYPES.__iter__().__next__())
    check("get_view_label format", lambda: "[" in m.get_view_label(v1))


# ---------------------------------------------------------------------------
# 8. operations.bulk_rename string helpers (pure Python, no Revit)
# ---------------------------------------------------------------------------

def test_bulk_rename_helpers():
    section("operations.bulk_rename (string helpers)")
    # Ensure dependencies for bulk_rename are pre-loaded
    if "anongee_toolkit.revit.application" not in sys.modules:
        load_module("revit/application.py")
    if "anongee_toolkit.revit.transactions" not in sys.modules:
        load_module("revit/transactions.py")
    if "anongee_toolkit.ui.xaml" not in sys.modules:
        load_module("ui/xaml.py")
    m = load_module("operations/bulk_rename.py")

    cs = m.replace_case_sensitive
    ci = m.replace_case_insensitive

    check("cs match",             lambda: cs("Hello World", "World", "Revit") == ("Hello Revit", True))
    check("cs no match",          lambda: cs("Hello World", "world", "X") == ("Hello World", False))
    check("cs empty replacement", lambda: cs("AnnA", "nn", "") == ("AA", True))
    check("ci match",             lambda: ci("Hello World", "hello", "Hi")[0] == "Hi World")
    check("ci changed flag",      lambda: ci("Hello World", "hello", "Hi")[1] is True)
    check("ci no match",          lambda: ci("Hello World", "xyz", "A") == ("Hello World", False))
    check("ci preserves case of replacement", lambda: ci("hello world", "WORLD", "Revit")[0] == "hello Revit")


# ---------------------------------------------------------------------------
# 9. __init__.__all__ completeness
# ---------------------------------------------------------------------------

def test_all_completeness():
    section("__init__.__all__ completeness")
    import ast

    init_path = os.path.join(TOOLKIT_DIR, "anongee_toolkit", "__init__.py")
    with open(init_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    # Collect names in __all__
    all_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__":
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant):
                            all_names.add(elt.value)

    check("__all__ has entries", lambda: len(all_names) > 30)
    check("__version__ in __all__", lambda: "__version__" in all_names)
    check("RevitTransaction in __all__", lambda: "RevitTransaction" in all_names)
    check("WpfDialogBase in __all__", lambda: "WpfDialogBase" in all_names)
    check("GenericBulkDeleteDialog in __all__", lambda: "GenericBulkDeleteDialog" in all_names)
    check("ExcelComWriter in __all__", lambda: "ExcelComWriter" in all_names)
    check("get_rebars in __all__", lambda: "get_rebars" in all_names)


# ---------------------------------------------------------------------------
# 10. Internal import graph (AST)
# ---------------------------------------------------------------------------

def test_import_graph():
    section("Internal import graph (all anongee_toolkit.* imports resolve)")
    import ast

    toolkit_root = os.path.join(TOOLKIT_DIR, "anongee_toolkit")
    all_modules  = set()

    for dirpath, _, files in os.walk(toolkit_root):
        for fname in files:
            if fname.endswith(".py"):
                fpath = os.path.join(dirpath, fname)
                rel   = os.path.relpath(fpath, TOOLKIT_DIR)
                dotted = rel.replace(os.sep, ".").removesuffix(".py")
                all_modules.add(dotted)

    missing = []
    for mod_path in sorted(all_modules):
        fpath = os.path.join(TOOLKIT_DIR, mod_path.replace(".", os.sep) + ".py")
        if not os.path.exists(fpath):
            continue
        with open(fpath, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("anongee_toolkit"):
                    # Convert to file path
                    target = node.module.replace(".", os.sep) + ".py"
                    if not os.path.exists(os.path.join(TOOLKIT_DIR, target)):
                        # Could be a package __init__
                        target_pkg = node.module.replace(".", os.sep) + os.sep + "__init__.py"
                        if not os.path.exists(os.path.join(TOOLKIT_DIR, target_pkg)):
                            missing.append("{} → {}".format(mod_path, node.module))

    if missing:
        for m in missing:
            fail("missing import target: " + m)
    else:
        ok("all internal imports resolve to existing files")


# ---------------------------------------------------------------------------
# 11. ui.forms (module import only — pure .NET forms)
# ---------------------------------------------------------------------------

def test_forms_import():
    section("ui.forms (import)")
    load_module("ui/__init__.py")
    try:
        m = load_module("ui/forms.py")
        ok("ui.forms imports cleanly")
        check("alert is callable",    lambda: callable(m.alert))
        check("confirm is callable",  lambda: callable(m.confirm))
        check("pick_file is callable", lambda: callable(m.pick_file))
        check("save_file is callable", lambda: callable(m.save_file))
    except Exception as e:
        fail("ui.forms import failed", e)


# ---------------------------------------------------------------------------
# 12. ui.dialogs (module import only)
# ---------------------------------------------------------------------------

def test_dialogs_import():
    section("ui.dialogs (import)")
    try:
        # ui.xaml must be loaded first (dialogs imports it)
        load_module("ui/xaml.py")
        m = load_module("ui/dialogs.py")
        ok("ui.dialogs imports cleanly")
        check("WpfDialogBase defined",  lambda: hasattr(m, "WpfDialogBase"))
        check("DebounceTimer defined",  lambda: hasattr(m, "DebounceTimer"))
        dt = m.DebounceTimer(lambda: None, 200)
        ok("DebounceTimer instantiates")
        dt.reset()
        ok("DebounceTimer.reset() callable")
        dt.stop()
        ok("DebounceTimer.stop() callable")
    except Exception as e:
        fail("ui.dialogs import/instantiation failed", e)


# ---------------------------------------------------------------------------
# cad2bim column-schedule parser (pure: no Revit / .NET)
# ---------------------------------------------------------------------------

def test_schedule():
    section("cad2bim column-schedule parser")
    try:
        from cad2bim import marks, layers
        from cad2bim.model import TextRecord
    except Exception as e:
        fail("cad2bim.marks / layers import", e)
        return

    def cell(text, x=0.0, y=0.0):
        return TextRecord(text, "S-COLS-SCHEDULE", (x, y, 0.0))

    # Inline cells (mark + size in one cell) are read directly.
    inline = marks.parse_schedule([cell("C1 400x600"), cell("C2 300x300")])
    check("inline cell sizes a mark",
          lambda: inline.get("C1") == (400.0, 600.0))
    check("two inline rows both captured",
          lambda: inline.get("C2") == (300.0, 300.0))

    # Split cells: mark and size in separate cells on the same table row.
    split = marks.parse_schedule([
        cell("C9", 0, 100), cell("400x600", 50, 100),
        cell("C10", 0, 90), cell("300x300", 50, 90)])
    check("split row pairs mark with its row's size",
          lambda: split.get("C9") == (400.0, 600.0))
    check("second split row pairs independently",
          lambda: split.get("C10") == (300.0, 300.0))

    # A size directly above/below a mark (same column) is NOT its size.
    same_col = marks.parse_schedule([cell("C5", 0, 100), cell("250x250", 0, 80)])
    check("same-column size is not paired across rows",
          lambda: "C5" not in same_col)

    # Inline reading wins over a stray split pairing for the same mark.
    prec = marks.parse_schedule([
        cell("C1 400x600", 0, 0), cell("C1", 0, 50), cell("999x999", 50, 50)])
    check("inline size wins over split on conflict",
          lambda: prec.get("C1") == (400.0, 600.0))

    check("empty input yields empty schedule",
          lambda: marks.parse_schedule([]) == {})
    check("None input yields empty schedule",
          lambda: marks.parse_schedule(None) == {})

    # Layer routing: a schedule layer must route to the new category, not plan text.
    check("schedule layer routes to column schedule",
          lambda: layers.classify_text_layer("S-COLS-SCHEDULE")
          == layers.CATEGORY_COLUMN_SCHEDULE)
    check("plain column layer still routes to column text",
          lambda: layers.classify_text_layer("S-COLS-IDEN")
          == layers.CATEGORY_COLUMN_TEXT)
    check("column schedule is an offered text category",
          lambda: layers.CATEGORY_COLUMN_SCHEDULE in layers.TEXT_CATEGORIES)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_syntax()
    test_units()
    test_helpers()
    test_application()
    test_compatibility()
    test_geometry()
    test_views()
    test_bulk_rename_helpers()
    test_all_completeness()
    test_import_graph()
    test_forms_import()
    test_dialogs_import()
    test_schedule()

    print("\n" + "=" * 60)
    print("Results: {} passed, {} failed".format(PASS, FAIL))
    if ERRORS:
        print("\nFailures:")
        for e in ERRORS:
            print(" ", e)
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)

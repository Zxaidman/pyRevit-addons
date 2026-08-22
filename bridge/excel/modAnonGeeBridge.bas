Attribute VB_Name = "modAnonGeeBridge"
' AnonGee Bridge - the Excel end of the spike (CRIT-1)
' ===========================================================================
' Two subs, and between them they answer whether an Excel button can reach
' Revit at all:
'
'   AnonGeeBridge_Ping     the Routes server, with no Revit in the question
'   AnonGeeBridge_Status   the open model, through Revit's own thread
'
' Ping deliberately asks for nothing from Revit. If Ping answers and Status
' does not, the server is fine and the External Event marshalling is not --
' which is the difference between knowing what to fix and guessing.
'
' Nothing here writes to a model and nothing here is the product. The real
' bridge posts a job and polls for a result; this proves the wire exists.
'
' HOW TO RUN
'   1. In Revit: pyRevit tab -> Settings -> turn the Routes server on, restart
'      Revit. (Confirming exactly where that switch is, is part of this spike.)
'   2. In Excel: Alt+F11 -> File -> Import File -> this .bas
'   3. Alt+F8 -> AnonGeeBridge_Ping -> Run
'
' KEEP THIS SMALL. Anything the macro knows is a thing that has to be kept in
' step with Python by hand. It marshals nothing and holds no data model, and
' it must stay that way -- the command envelope carries which sheet to read,
' and Revit opens the workbook itself with the reader that already exists.
' ===========================================================================

Option Explicit

' The host and path also live in AnonGee.extension/startup.py, and a test in
' tests/test_bridge.py holds the two together. A URL that disagrees with its
' route costs an afternoon and looks like a network problem the whole time.
Public Const BRIDGE_HOST As String = "localhost"
Public Const BRIDGE_PORT As Long = 48884
Public Const BRIDGE_API As String = "anongee"

' Long enough for Revit to finish what it is doing, short enough that a user
' does not think Excel has hung. The real bridge posts and polls instead of
' waiting, precisely because this number can never be right for every job.
Public Const BRIDGE_TIMEOUT_SECONDS As Long = 15


Public Function BridgeUrl(ByVal route As String) As String
    BridgeUrl = "http://" & BRIDGE_HOST & ":" & CStr(BRIDGE_PORT) & _
                "/" & BRIDGE_API & "/" & route
End Function


' --- the two spike commands ------------------------------------------------

Public Sub AnonGeeBridge_Ping()
    Dim body As String
    body = HttpGet(BridgeUrl("ping"))
    ReportToSheet "PING", body
End Sub


Public Sub AnonGeeBridge_Status()
    Dim body As String
    body = HttpGet(BridgeUrl("status"))
    ReportToSheet "STATUS", body
End Sub


' --- the wire --------------------------------------------------------------

Public Function HttpGet(ByVal url As String) As String
    ' WinHttp first: it is the only one of the two with a settable timeout,
    ' and without one a busy Revit hangs Excel with no way back.
    On Error GoTo UseMsxml

    Dim winHttp As Object
    Set winHttp = CreateObject("WinHttp.WinHttpRequest.5.1")
    winHttp.SetTimeouts BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000, _
                        BRIDGE_TIMEOUT_SECONDS * 1000
    winHttp.Open "GET", url, False
    winHttp.Send
    HttpGet = winHttp.ResponseText
    Exit Function

UseMsxml:
    On Error GoTo Failed
    Dim msxml As Object
    Set msxml = CreateObject("MSXML2.XMLHTTP")
    msxml.Open "GET", url, False
    msxml.Send
    HttpGet = msxml.ResponseText
    Exit Function

Failed:
    ' The failure is the answer here, so it is returned rather than raised.
    ' "Nothing is listening" and "Revit is busy" look identical from Excel and
    ' are told apart by whether Ping answers while Status does not.
    HttpGet = "{""ok"": false, ""error"": """ & _
              Replace(Err.Description, """", "'") & """, ""url"": """ & url & """}"
End Function


' --- reporting -------------------------------------------------------------

Private Sub ReportToSheet(ByVal label As String, ByVal body As String)
    Dim sheet As Worksheet
    Set sheet = EnsureSheet("BRIDGE_SPIKE")

    Dim row As Long
    row = sheet.Cells(sheet.Rows.Count, 1).End(xlUp).row + 1
    If row < 2 Then
        sheet.Cells(1, 1).Value = "When"
        sheet.Cells(1, 2).Value = "Call"
        sheet.Cells(1, 3).Value = "OK"
        sheet.Cells(1, 4).Value = "Engine"
        sheet.Cells(1, 5).Value = "Document"
        sheet.Cells(1, 6).Value = "Raw response"
        sheet.Rows(1).Font.Bold = True
        row = 2
    End If

    sheet.Cells(row, 1).Value = Now
    sheet.Cells(row, 2).Value = label
    sheet.Cells(row, 3).Value = JsonValue(body, "ok")
    sheet.Cells(row, 4).Value = JsonValue(body, "version")
    sheet.Cells(row, 5).Value = JsonValue(body, "title")
    sheet.Cells(row, 6).Value = body
    sheet.Columns("A:E").AutoFit

    MsgBox label & ": " & Left$(body, 400), vbInformation, "AnonGee Bridge"
End Sub


Private Function EnsureSheet(ByVal name As String) As Worksheet
    On Error Resume Next
    Set EnsureSheet = ThisWorkbook.Worksheets(name)
    On Error GoTo 0
    If EnsureSheet Is Nothing Then
        Set EnsureSheet = ThisWorkbook.Worksheets.Add( _
            After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
        EnsureSheet.name = name
    End If
End Function


' --- NOT a JSON parser -----------------------------------------------------
' It finds the first "key": value pair and returns the value as text. Good
' enough to put four fields in four cells for a spike, and no further. VBA has
' no JSON parser; the real bridge needs one, and writing half of it here would
' be the worst of both -- so this is deliberately named for what it is not.

Public Function JsonValue(ByVal body As String, ByVal key As String) As String
    Dim marker As String
    marker = """" & key & """"

    Dim at As Long
    at = InStr(1, body, marker, vbTextCompare)
    If at = 0 Then
        JsonValue = ""
        Exit Function
    End If

    Dim colon As Long
    colon = InStr(at + Len(marker), body, ":")
    If colon = 0 Then
        JsonValue = ""
        Exit Function
    End If

    Dim rest As String
    rest = LTrim$(Mid$(body, colon + 1))

    If Left$(rest, 1) = """" Then
        Dim closing As Long
        closing = InStr(2, rest, """")
        If closing = 0 Then
            JsonValue = ""
        Else
            JsonValue = Mid$(rest, 2, closing - 2)
        End If
        Exit Function
    End If

    Dim ends As Long
    ends = Len(rest) + 1
    Dim index As Long
    Dim ch As String
    For index = 1 To Len(rest)
        ch = Mid$(rest, index, 1)
        If ch = "," Or ch = "}" Or ch = "]" Then
            ends = index
            Exit For
        End If
    Next index
    JsonValue = Trim$(Left$(rest, ends - 1))
End Function

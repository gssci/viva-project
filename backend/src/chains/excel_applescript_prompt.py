excel_system_mgs = """# 📘 Microsoft Office AppleScript Integration: Master Reference Guide

This document serves as a technical reference and set of strict guidelines for writing AppleScript code to automate Microsoft Office (Excel, Word, PowerPoint) on macOS. It focuses on the Object Model, Command Syntax, and known dictionary quirks.

---

## 1. Fundamental Core Concepts
*   **The Dictionary:** Every Office app has an internal AppleScript dictionary. Always use a `tell application "Microsoft [App]"` block.
*   **The Object Model (Containment):** Office follows a strict hierarchy. You must drill down from the Application to the specific Element.
    *   *Example:* `Cell` belongs to `Sheet`, which belongs to `Workbook`, which belongs to `Application`.
*   **Properties vs. Elements:** An object has **Properties** (fixed traits like `name`, `color`) and **Elements** (contained objects like `paragraphs` or `cells`).
*   **Referencing:** Use `set` to define variables for objects to avoid repetitive nesting.

---

## 2. Microsoft Excel: The Complete Reference
Excel is the most scriptable Office app. Its primary object is the **Range**.
*   **Hierarchy:** `Application` ➔ `Workbook` ➔ `Worksheet` ➔ `Range` (Row/Column/Cell) ➔ `Elements`

### File & Sheet Management
```applescript
tell application "Microsoft Excel"
    -- Create and Open
    set myBook to make new workbook
    open POSIX file "/Users/User/Desktop/Data.xlsx"
    
    -- Rename and Create Sheets
    set name of active sheet to "Summary"
    set newSheet to make new worksheet at end of active workbook
end tell
```

### Range & Data Manipulation
```applescript
tell application "Microsoft Excel"
    tell active sheet
        -- Write data (Single, Row, 2D Array)
        set value of range "A1" to "Total Revenue"
        set value of range "A2:C2" to {"Jan", "Feb", "Mar"}
        set value of range "A3:B4" to {{"Apples", 50}, {"Oranges", 30}}
        
        -- Formatting
        tell font object of range "A1:C1"
            set bold to true
            set font color to {255, 255, 255} -- RGB array
        end tell
        tell interior object of range "A1:C1"
            set color to {0, 100, 200}
        end tell
        autofit column "A:C"
        
        -- Sorting
        sort range "A1:C100" key1 range "B1" order1 sort descending header header yes
    end tell
end tell
```

### Advanced: Finding Last Row (Appending Data)
```applescript
tell application "Microsoft Excel"
    tell active sheet
        -- Simulates Cmd+Up from the bottom of Column A to find the last used row
        set lastRow to first row index of (get end (cell (count rows) of column 1) direction toward the top)
        set nextEmptyRow to lastRow + 1
        set value of cell ("A" & nextEmptyRow) to "New Entry"
    end tell
end tell
```

### Advanced: Charting & Data Plots (CRITICAL DICTIONARY QUIRKS)
*   **Quirk 1:** Vertical positioning is `top`, NOT `top position` (horizontal is `left position`).
*   **Quirk 2:** Binding data is an action command: `set source data [chart] source [range]`.
*   **Quirk 3:** `caption` is read-only. Target `chart title text` of the `chart title` object.

```applescript
tell application "Microsoft Excel"
    tell active sheet
        set chartData to range "A1:B5"
        
        -- 1. Create the Chart Container
        set myChartObj to make new chart object at active sheet with properties {left position:150, top:20, width:400, height:250}
        
        -- 2. Bind the Data (Must be outside the 'tell chart' block)
        set source data chart of myChartObj source chartData
        
        -- 3. Format the Chart Design
        tell chart of myChartObj
            set chart type to column clustered -- Other types: line markers, pie
            set has title to true
            tell its chart title
                set chart title text to "Q1 Sales Trend"
            end tell
        end tell
    end tell
end tell
```

---

## 3. Microsoft Word: Text, Structure & Tables
Word scripts revolve around the **Text Object**, **Selection**, and **Tables**.
*   **Hierarchy:** `Application` ➔ `Document` ➔ `Section` ➔ `Text Object` / `Paragraph` / `Table`

### Document Generation & Formatting
```applescript
tell application "Microsoft Word"
    set myDoc to make new document
    set myRange to text object of myDoc
    insert text "Report Title" & return at end of myRange
    set style of paragraph 1 of myDoc to style heading1
end tell
```

### Advanced: Table Generation
Create the structure first, then inject text and format rows/cells.
```applescript
tell application "Microsoft Word"
    set newDoc to make new document
    set newTable to make new table at newDoc with properties {text object:(text object of newDoc), number of rows:2, number of columns:2}
    
    set content of text object of cell 1 of row 1 of newTable to "Name"
    set bold of font object of row 1 of newTable to true
    set texture of shading object of row 1 of newTable to texture 10 percent
    
    auto fit behavior newTable behavior auto fit content
end tell
```

### Advanced: Find & Replace with Formatting
Always clear formatting criteria before executing a search.
```applescript
tell application "Microsoft Word"
    set myFind to find object of text object of active document
    clear formatting myFind
    clear formatting replacement of myFind
    
    set content of myFind to "Confidential"
    set content of replacement of myFind to "RESTRICTED"
    set bold of font object of replacement of myFind to true
    
    execute find myFind replace replace all
end tell
```

---

## 4. Microsoft PowerPoint: Slides & Shapes
Everything in PowerPoint is a **Shape** inside a **Slide**.
*   **Hierarchy:** `Application` ➔ `Presentation` ➔ `Slide` ➔ `Shape` ➔ `Text Frame` ➔ `Text Range`

### Slide Creation & Text Injection
You must target the `text range` within the `text frame` of a shape.
```applescript
tell application "Microsoft PowerPoint"
    set myPres to make new presentation
    set mySlide to make new slide at end of myPres with properties {layout:slide layout title slide}
    
    -- Shape 1 is typically the Title box
    set content of text range of text frame of shape 1 of mySlide to "Quarterly Review"
end tell
```

---

## 5. File Operations: Saving, PDF Export, & Sharing

```applescript
-- Save and Export PDF (Excel Example, Word is similar using 'active document')
tell application "Microsoft Excel"
    save active workbook in POSIX file "/Users/Username/Desktop/Report.xlsx"
    save as active sheet filename "/Users/Username/Desktop/Report.pdf" file format PDF file format
end tell

-- Share via Apple Mail
tell application "Microsoft Word" to set docPath to (full name of active document)
tell application "Mail"
    set newMessage to make new outgoing message with properties {subject:"Report", content:"Attached.", visible:true}
    tell newMessage
        make new to recipient with properties {address:"team@company.com"}
        make new attachment with properties {file name:(docPath as alias)}
    end tell
end tell
```

---

## 6. Strict Rules for LLM Code Generation
1.  **File Paths:** ALWAYS use `POSIX file "/path/to/file"` or coerce to `alias`. Do not use raw strings for paths in `open` or `save` commands.
2.  **Properties at Creation:** When creating objects, pass properties in a record immediately: `make new [object] with properties {name:"Test"}`.
3.  **UI Scripting:** If a requested action (e.g., clicking a specific Ribbon button) does not exist in the Object Model, use standard System Events UI scripting as a fallback.
4.  **Error Handling:** Wrap file operations or complex searches in `try... on error... end try` blocks."""
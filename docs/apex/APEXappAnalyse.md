# APEX Application Analysis — Master/Detail Setup (Applications → Pages)

## Goal

Create a master–detail page in Oracle APEX where:

- Applications = master Interactive Report  
- Pages = detail Interactive Report  
- Selecting an application filters its pages  
- Changing filters clears the selection  
- Row button “Load” executes server logic for the selected application  

---

## 1. Master Region — Applications

Interactive Report based on APEX metadata (example: `apex_applications`).

### Link on Application ID column

Create a link that sets page items:

- `P08_APPLICATION_ID = #APPLICATION_ID#`
- `P8_WORKSPACE = #WORKSPACE#`
- `P8_PROJECT_NAME = APEX`

Optional request:

- `Request = RUN_PREPARE_APEX_ALL`

---

## 2. Page Items (State Holders)

Create hidden items:

- `P08_APPLICATION_ID`
- `P8_WORKSPACE`
- `P8_PROJECT_NAME`

These store the selected master row values.

---

## 3. Detail Region — Pages

Interactive Report on `apex_application_pages`.

### SQL Query

```sql
SELECT
    application_id,
    workspace,
    application_name,
    page_id,
    page_name,
    page_mode,
    page_alias,
    page_group,
    last_updated_on,
    'Load' AS load_action
FROM apex_application_pages
WHERE :P08_APPLICATION_ID IS NOT NULL
  AND application_id = :P08_APPLICATION_ID
ORDER BY application_id, page_id;
```

### Important Region Setting

Page Items to Submit:

```
P08_APPLICATION_ID,P8_WORKSPACE,P8_PROJECT_NAME
```

---

## 4. Load Button per Row (Report Column)

Create a column **LOAD_ACTION** as Link:

- Link Text: `Load`
- Target: Same Page
- Set Items:

```
P08_APPLICATION_ID = #APPLICATION_ID#
P8_WORKSPACE = #WORKSPACE#
P8_PROJECT_NAME = #APPLICATION_NAME#
Request = RUN_PREPARE_APEX_ALL
```

---

## 5. Server Process (Run on Request)

Create a process:

- Name: `RUN_PREPARE_APEX_ALL`
- Point: After Submit
- Server-side Condition → When Button Pressed:
  - Use Request = `RUN_PREPARE_APEX_ALL`

Example PL/SQL:

```plsql
DECLARE
    l_regions_job NUMBER;
    l_buttons_job NUMBER;
BEGIN
    Y055490.NEO4JUTILS.PREPARE_APEX_ALL(
        PN_APP_ID        => :P08_APPLICATION_ID,
        pv_workspace     => :P8_WORKSPACE,
        pv_project_name  => :P8_PROJECT_NAME,
        PN_JOBID_REGIONS => l_regions_job,
        PN_JOBID_BUTTONS => l_buttons_job
    );

    apex_application.g_print_success_message :=
        'Prepare APEX finished. REGIONS job id: ' || l_regions_job ||
        ', BUTTONS job id: ' || l_buttons_job;
END;
```

---

## 6. Clear Selection When Master Changes

Problem: Filtering Applications does not automatically clear previously selected application.

### Dynamic Action — After Refresh (Applications Region)

Event:

- After Refresh  
- Selection Type: Region  
- Region: Applications  

#### True Action 1 — Execute Server-side Code

```plsql
:P08_APPLICATION_ID := NULL;
:P8_WORKSPACE := NULL;
:P8_PROJECT_NAME := NULL;
```

Items to Submit:

```
P08_APPLICATION_ID,P8_WORKSPACE,P8_PROJECT_NAME
```

Items to Return:

```
P08_APPLICATION_ID,P8_WORKSPACE,P8_PROJECT_NAME
```

Enable:

- Wait for Result = Yes

#### True Action 2 — Refresh Pages Region

Action: Refresh  
Selection Type: Region  
Region: Pages  

---

## 7. Static ID (Recommended)

Assign Static ID to Pages region:

```
PAGES_RGN
```

Useful for JavaScript:

```javascript
apex.region("PAGES_RGN").refresh();
```

---

## Result

- Applications acts as master  
- Pages shows only selected application's pages  
- Changing filters clears selection  
- No stale session state values  
- Row-level Load action triggers processing correctly  

---

## Notes

- Always include dependent items in Page Items to Submit  
- Use server-side clearing when session state must be reset  
- Prefer declarative Refresh actions over custom JavaScript when possible  

// Interface walkthroughs (generated from the eight walkthrough HTML files): steps, click sequences and notes.
// Each step opens the real screen (route) and highlights the control to use (focus).
// eslint-disable-next-line no-unused-vars
const WALKTHROUGHS = [
 {
  "key": "admin",
  "title": "Platform Settings & Administration",
  "steps": [
   {
    "tab": "1 · Admin home",
    "title": "Administration center",
    "how": [
     "Open Administration from the side menu.",
     "Start with Organization and Org structure; then users, app permissions, configuration and monitoring.",
     "Needs attention lists what to fix first."
    ],
    "note": "Each area appears only for the roles that manage it.",
    "route": "admin",
    "focus": "Manage"
   },
   {
    "tab": "2 · Organization",
    "title": "Organization profile",
    "how": [
     "Administration → Organization.",
     "Check instance name, locale, time zone, fiscal year end and the names printed on reports; branding opens the App catalogue.",
     "Click Save changes."
    ],
    "note": "The address is set on the server; links in e-mails use it. The instance name needs a Super Administrator.",
    "route": "organization",
    "focus": "Save changes"
   },
   {
    "tab": "3 · Org structure",
    "title": "Organization structure and entity tagging",
    "how": [
     "Administration → Org structure.",
     "Click Manage categories to define entity types such as port, department or unit.",
     "Click + New Entity, enter its name, category, optional parent and description, then Create.",
     "Build parent/child levels consistently so coverage reports are meaningful."
    ],
    "note": "Categories in the org tree form the audit universe. A new entity waits for approval.",
    "route": "orgstructure",
    "focus": "+ New Entity"
   },
   {
    "tab": "4 · Users & groups",
    "title": "People and group membership",
    "how": [
     "Administration → Users & access → Users.",
     "Click + Add user, enter a unique email, choose the platform user type and optionally groups.",
     "Click Send invitation; the person activates the link and sets a password. Without e-mail, copy the link shown once.",
     "Check Licenses before inviting: a full role refuses new people."
    ],
    "note": "New accounts are invited: the person activates the e-mailed link and chooses their own password. Licensed seats per role are checked first.",
    "route": "usersAdd",
    "focus": "Send invitation"
   },
   {
    "tab": "5 · Roles & licenses",
    "title": "Grant the right access at each layer",
    "how": [
     "Users & access → Application permissions.",
     "Assign app access gives one person a role; Manage group roles gives every member of a group the same role.",
     "Choose the narrowest suitable role; project access then follows the person's port and engagement teams.",
     "Verify in Users & access."
    ],
    "note": "Each person holds one role; groups never add permissions. Manage group roles changes every member's own role, with the same checks.",
    "route": "roles",
    "focus": "Assign app access"
   },
   {
    "tab": "6 · Profile & security",
    "title": "Personal details and sign-in",
    "how": [
     "Open My profile from your name in the top bar.",
     "Update name, email or locale and click Save profile.",
     "Change password, set up two-step sign-in and review your sign-in history on the same page."
    ],
    "note": "",
    "route": "profile",
    "focus": "Save profile"
   },
   {
    "tab": "7 · App configuration",
    "title": "Configure apps where the work happens",
    "how": [
     "Administration → App settings.",
     "Open the app's settings page: project types, entities, workflow, risk scoring, follow-up and reports.",
     "Review the current values before editing.",
     "Save, then check the effect on a pilot record."
    ],
    "note": "Each app keeps its own settings; what you can change depends on your role.",
    "route": "appsettings",
    "focus": "Open Projects settings"
   },
   {
    "tab": "8 · Imports & limits",
    "title": "Import structured resources carefully",
    "how": [
     "Data & activity → Bulk Importer.",
     "Choose the resource type; click Download .xlsx template and fill it without changing headers.",
     "Upload the populated template, click Validate & upload, review the preview, then Import.",
     "Check Data limitations before loading large files."
    ],
    "note": "",
    "route": "imports",
    "focus": "Validate & upload"
   },
   {
    "tab": "9 · Activity trail",
    "title": "Audit trail of platform changes",
    "how": [
     "Data & activity → Activity logs.",
     "Filter by activity type, user and date range; click Apply filters.",
     "Click View on a row to see what changed, who changed it and when.",
     "Click Download activity log for review and retention."
    ],
    "note": "Every download of the activity log is itself recorded.",
    "route": "logs",
    "focus": "Apply filters"
   },
   {
    "tab": "10 · Cycle close & recovery",
    "title": "Complete the cycle and prepare the next one",
    "how": [
     "Administration → Cycle close.",
     "Confirm project statuses and sign-offs, and that open issues and actions have owners and due dates.",
     "Download the activity log the evidence pack needs and file it in the records repository.",
     "Check the next fiscal year end, entities, user access and seats, then Start next planning cycle."
    ],
    "note": "Backups and restores run on this workspace's own server (Backup & recovery). A restore brings back the whole database, not one deleted record.",
    "route": "closeout",
    "focus": "Start next planning cycle"
   }
  ]
 },
 {
  "key": "plans",
  "title": "Assurance Plans",
  "steps": [
   {
    "tab": "1 · Prep",
    "title": "Prepare only what your plan needs",
    "how": [
     "Confirm your role allows you to create a plan.",
     "Set up entity tagging if you want entity coverage.",
     "Link framework objectives to strategic risks if you want risk alignment.",
     "Open the Assurance Plans app from Workspace Apps."
    ],
    "note": "An Assurance Plans Admin who is not also a Project Creator can link projects, but cannot create or roll forward them.",
    "route": "plansStart",
    "focus": null
   },
   {
    "tab": "2 · Create plan",
    "title": "Create new plan",
    "how": [
     "Click + Create plan.",
     "Enter plan name, optional description, available hours, and start/end dates.",
     "Click Create plan."
    ],
    "note": "",
    "route": "planCreate",
    "focus": "Create plan"
   },
   {
    "tab": "3 · Add projects",
    "title": "Plan created — now add projects",
    "how": [
     "Click + Add to plan.",
     "Choose a project path. The next screens show each path."
    ],
    "note": "",
    "route": "planOverviewNew",
    "focus": "+ Add to plan"
   },
   {
    "tab": "4 · New project",
    "title": "New project · Basic information",
    "how": [
     "Choose Create a new project from + Add to plan.",
     "Enter the project’s basic information.",
     "Click Continue."
    ],
    "note": "The specific project fields depend on your project type and organization settings.",
    "route": "newProject",
    "focus": "Continue"
   },
   {
    "tab": "5 · Objectives & entities",
    "title": "Select frameworks, objectives, and organizational coverage",
    "how": [
     "Select framework objectives, if available, then click Continue.",
     "Select entities that apply to this project, then click Continue.",
     "If you have no objectives or entities yet, the guide allows you to continue and add them later."
    ],
    "note": "",
    "route": "newProjectObjectives",
    "focus": "Continue"
   },
   {
    "tab": "6 · Link / roll forward",
    "title": "Choose an existing project path",
    "how": [
     "For linking, select active projects and click Link projects.",
     "For rollforward, search/filter, select the source, click Continue, enter new details, then click Save and rollforward project."
    ],
    "note": "",
    "route": "planLink",
    "focus": "Link projects"
   },
   {
    "tab": "7 · Objectives",
    "title": "Objectives organize project work",
    "how": [
     "Open a project and click Fieldwork.",
     "Click Add Objective.",
     "Enter the objective fields, then click Save.",
     "Click Import Objective, select a source project/framework/Project Library.",
     "Select objectives, optionally include project results, then click Import."
    ],
    "note": "Clone: open an objective with Go To → Overview, scroll to the bottom, choose Clone Objective, select target organization/project, then Clone. Clone copies one at a time; import can copy multiple.",
    "route": "objectiveList",
    "focus": "Add Objective"
   },
   {
    "tab": "8 · Narrative",
    "title": "Add a narrative",
    "how": [
     "Open an Internal Control workflow project and click Fieldwork.",
     "Beside the objective, click Go To → Narratives.",
     "Click Add new narrative, enter a title, then click Save.",
     "To add description or supporting files, edit the narrative and save the changes."
    ],
    "note": "Narratives are only available for projects/frameworks using the Internal Control workflow.",
    "route": "narratives",
    "focus": "Add new narrative"
   },
   {
    "tab": "9 · Coverage",
    "title": "Coverage monitoring",
    "how": [
     "Open the assurance plan.",
     "Under Show coverage in, select Entities or Categories.",
     "Choose the entity/category filter. Projects appear with their tagged coverage."
    ],
    "note": "",
    "route": "planCoverage",
    "focus": "Coverage view"
   },
   {
    "tab": "10 · Risks",
    "title": "Strategic risks",
    "how": [
     "Open the plan.",
     "Click the Risks tab to review linked strategic risks."
    ],
    "note": "",
    "route": "planRisks",
    "focus": null
   },
   {
    "tab": "11 · Progress & hours",
    "title": "Annual Program Overview",
    "how": [
     "Review project progress, plan completion, and available resources.",
     "Use the coverage controls to switch entity/category views.",
     "Open Risks to review strategic-risk alignment."
    ],
    "note": "",
    "route": "planOverview",
    "focus": "View by individual entity"
   }
  ]
 },
 {
  "key": "projects",
  "title": "Projects",
  "steps": [
   {
    "tab": "1 · Open project",
    "title": "Open a project from your assurance plan",
    "how": [
     "Open the project linked to the Assurance Plan.",
     "On its project dashboard, review tabs and assigned objectives.",
     "Continue in Fieldwork to perform the project work."
    ],
    "note": "",
    "route": "audits",
    "focus": "Search projects"
   },
   {
    "tab": "2 · Choose workflow",
    "title": "Confirm the project workflow",
    "how": [
     "Check the project type/workflow with your project administrator if unsure.",
     "For Workplan projects, use Execute Procedures.",
     "For Internal Control projects, use walkthroughs and tests."
    ],
    "note": "The workflow determines which project components appear. Your organization may customize tab names and fields.",
    "route": "projectSettings",
    "focus": null
   },
   {
    "tab": "3 · Open Fieldwork",
    "title": "Fieldwork · objective list",
    "how": [
     "Click Fieldwork.",
     "Find the relevant objective.",
     "Click Go To and choose the relevant page, such as procedure, walkthrough, test plan, or testing round."
    ],
    "note": "",
    "route": "objectiveList",
    "focus": "Go To"
   },
   {
    "tab": "4 · Execute / test",
    "title": "Perform a test (Internal Control workflow)",
    "how": [
     "On Fieldwork, click Go To beside the process and select Interim Testing or Final Testing.",
     "Select the appropriate round and click Update Test.",
     "Enter test results, conclusion, and optional supporting files; then click Save.",
     "Wait for each save confirmation before editing another field."
    ],
    "note": "Workplan projects use Execute Procedures instead. Exact test fields depend on configuration.",
    "route": "testing",
    "focus": "Update Test"
   },
   {
    "tab": "5 · Evidence & requests",
    "title": "Collect and attach evidence",
    "how": [
     "In the project, open Requests from the upper-right Utility Toolbar.",
     "Click + New request, describe the document needed, assign an owner, and click Save.",
     "Attach received evidence to the relevant work page."
    ],
    "note": "Requests can also be opened from Planning, Fieldwork, or Results. AI request generation is optional and requires an administrator to enable AI features.",
    "route": "requests",
    "focus": "+ New request"
   },
   {
    "tab": "6 · Record issue",
    "title": "Record an issue or control gap",
    "how": [
     "Open the relevant Fieldwork page, then click Issues in the Utility Toolbar.",
     "In the side panel, click + Add Issue.",
     "Record basic issue information, assign an owner, and save."
    ],
    "note": "Associating an issue with fieldwork lets it appear in related assurance views. A standalone issue added from the Issues tab may not appear in those fieldwork-linked views.",
    "route": "issuesPanel",
    "focus": "+ Add Issue"
   },
   {
    "tab": "7 · Remediate & retest",
    "title": "Management response and remediation",
    "how": [
     "Open the issue’s Follow-up & Remediation subtab.",
     "Record management response, action owner, and target timing.",
     "After corrective work, use Retest Information to record the retest and closure assessment."
    ],
    "note": "",
    "route": "issueRemediation",
    "focus": "Save"
   },
   {
    "tab": "8 · Review & sign off",
    "title": "Sign off and assign the next reviewer",
    "how": [
     "Finish documenting the page and open its Sign-offs area.",
     "Click the sign-off link for your assigned review level.",
     "Select a Next Reviewer and click Set and Notify Reviewer.",
     "Use Projects status to track assigned work and reviews."
    ],
    "note": "After initial sign-off, an individual item page becomes read-only. The review chain and permissions depend on roles and configuration.",
    "route": "signoffs",
    "focus": "Set and Notify Reviewer"
   },
   {
    "tab": "9 · Results & reports",
    "title": "Review results and prepare reporting",
    "how": [
     "Review and sign off on project work.",
     "Open Results / Fieldwork Reports for project outputs.",
     "For organization-wide reporting, continue to the separate Reports app walkthrough."
    ],
    "note": "",
    "route": "results",
    "focus": "Results"
   }
  ]
 },
 {
  "key": "reports",
  "title": "Reports",
  "steps": [
   {
    "tab": "1 · Open Reports",
    "title": "Reports · Browse",
    "how": [
     "From Workspace Apps, open the Reports app.",
     "Select Create → Report to start from scratch, or browse for a template."
    ],
    "note": "Only audit staff can create reports.",
    "route": "reportsBrowse",
    "focus": "Create"
   },
   {
    "tab": "2 · Choose a starting point",
    "title": "Choose a starting point",
    "how": [
     "For a template, open Templates → Report Templates.",
     "Right-click a suitable template and choose Make a copy.",
     "For a new report, choose Create → Report."
    ],
    "note": "Templates can help you start from a report structure that already matches a common use case.",
    "route": "reportsTemplates",
    "focus": "Make a copy"
   },
   {
    "tab": "3 · Choose a view",
    "title": "Select a View",
    "how": [
     "In the New Report dialog, select the appropriate View.",
     "The Report Builder opens on the Data tab."
    ],
    "note": "The available Views and field folders depend on the data available to your organization.",
    "route": "builderReport",
    "focus": "View"
   },
   {
    "tab": "4 · Build the table",
    "title": "Build the report table",
    "how": [
     "Search or expand the field folders.",
     "Drag fields into Columns and/or Rows; optional fields can go into Sections or Filters.",
     "Reorder or aggregate fields as needed, then preview the data.",
     "Finish the table layout before adding charts."
    ],
    "note": "Changing a Column or Row layout to Cross Tab after creating charts permanently deletes those charts.",
    "route": "builderData",
    "focus": null
   },
   {
    "tab": "5 · Add a chart",
    "title": "Visualize the report data",
    "how": [
     "Click Charts.",
     "Keep Auto Chart selected or choose a chart type.",
     "Drag fields already included in the Data tab into chart areas, then format the chart."
    ],
    "note": "",
    "route": "builderCharts",
    "focus": "Chart type"
   },
   {
    "tab": "6 · Design preview",
    "title": "Review and format",
    "how": [
     "Click Design.",
     "Use the formatting toolbar to adjust the report.",
     "Review the output before publishing."
    ],
    "note": "",
    "route": "builderDesign",
    "focus": "Font"
   },
   {
    "tab": "7 · Publish and access",
    "title": "Set report details and access",
    "how": [
     "Click Publish.",
     "Enter a name, choose a folder, and set access.",
     "Review Distribution, Export, and Report Settings.",
     "Choose Save → Draft to keep editing, or Save → Activate to make it available to authorized users."
    ],
    "note": "Some folders require approval before a report can be activated.",
    "route": "builderPublish",
    "focus": "Save → Activate"
   },
   {
    "tab": "8 · Share / dashboard",
    "title": "Share the activated report",
    "how": [
     "Open the activated report.",
     "Use email or broadcast to distribute it, subject to your access settings.",
     "To show it with other reports/charts, add it to a dashboard."
    ],
    "note": "",
    "route": "reportView",
    "focus": "Add to dashboard"
   },
   {
    "tab": "9 · Optional AI Reporting",
    "title": "Optional: use AI Reporting",
    "how": [
     "Choose New report.",
     "Select a template or describe a report request.",
     "Review and confirm the suggested data sources.",
     "Wait for generation, review the draft, then publish or download PDF."
    ],
    "note": "AI Reporting is an optional, separate report-building experience. Its available templates and data sources can vary; the classic Report Builder sequence remains the preceding screens.",
    "route": "aiNew",
    "focus": "Use template"
   }
  ]
 },
 {
  "key": "dashboards",
  "title": "Dashboards & Presentations",
  "steps": [
   {
    "tab": "1 · Create dashboard",
    "title": "Create a stakeholder dashboard",
    "how": [
     "Open Reports from Workspace Apps.",
     "Click Create → Dashboard.",
     "Enter a name or continue to name it later."
    ],
    "note": "You need the audit staff role to create dashboards. Readers need access to the dashboard’s folder or explicit private access.",
    "route": "reportsBrowse",
    "focus": "Create"
   },
   {
    "tab": "2 · Choose layout",
    "title": "Name and choose a layout",
    "how": [
     "Name the dashboard tab.",
     "Choose a dashboard canvas or a static layout.",
     "Click Create."
    ],
    "note": "",
    "route": "dashCreate",
    "focus": "Select canvas"
   },
   {
    "tab": "3 · Add reports",
    "title": "Add published reports to the dashboard",
    "how": [
     "Open the dashboard in edit mode.",
     "Click Reports in the side panel and search or filter.",
     "Drag a report into the dashboard content area.",
     "Select a report visualization if it has multiple charts or tables; adjust position and size."
    ],
    "note": "A report must already exist; current report/chart updates are reflected when the dashboard is opened.",
    "route": "dashReports",
    "focus": null
   },
   {
    "tab": "4 · Add filters & context",
    "title": "Add filters and supporting context",
    "how": [
     "Use the side-panel widget categories to add filters, text, graphics, images, or supported widgets.",
     "Drag each item to the dashboard and configure it in the Properties panel.",
     "For linked filtering across several reports, the reports need compatible User Prompt filters."
    ],
    "note": "Shapes and lines are not supported in this dashboard builder. Feature availability depends on selected layout.",
    "route": "dashFilters",
    "focus": "+ Filter"
   },
   {
    "tab": "5 · Preview",
    "title": "Check the stakeholder view before publishing",
    "how": [
     "Click Preview Mode to test appearance and interactions.",
     "Confirm report widgets, filters, and all dashboard tabs work as intended.",
     "Return to the builder to make changes."
    ],
    "note": "",
    "route": "dashPreview",
    "focus": "Preview"
   },
   {
    "tab": "6 · Publish dashboard",
    "title": "Save and set audience access",
    "how": [
     "Click Publish.",
     "Enter dashboard name, description, and folder.",
     "Set public or private access; for private, choose users/groups under User Access.",
     "Choose Save → Draft or Save → Activate."
    ],
    "note": "To activate, each dashboard subtab must contain content. A draft can be saved while you continue editing.",
    "route": "dashPublish",
    "focus": "Save → Activate"
   },
   {
    "tab": "7 · Create a Present",
    "title": "Create a stakeholder presentation",
    "how": [
     "In Reports, choose Create → Present.",
     "Enter a name and optionally select a theme.",
     "Click Create."
    ],
    "note": "Present is the current presentation module; existing Storyboards remain available as read-only. You need audit staff access.",
    "route": "presentCreate",
    "focus": "Create"
   },
   {
    "tab": "8 · Build slides",
    "title": "Add slides and place content",
    "how": [
     "Open Slides, choose New, name the slide, and click Create.",
     "Click Reports, then drag a report/chart into the slide; resize and position it.",
     "Add concise text or other rich content for context.",
     "Reorder slides by dragging them in the Slides panel."
    ],
    "note": "Aim for one clear point per slide and keep the number of tables/charts limited so stakeholders can read the message quickly.",
    "route": "presentSlides",
    "focus": "New"
   },
   {
    "tab": "9 · Publish & present",
    "title": "Preview, activate, and share",
    "how": [
     "Preview the presentation and check slide order and readability.",
     "Click Publish; set name, description, folder, and access.",
     "Save as draft or activate for permitted viewers.",
     "Present to stakeholders; linked report/chart updates appear when the presentation is opened."
    ],
    "note": "Dashboard and Present are communication surfaces in Reports. They do not change the source project data.",
    "route": "presentPublish",
    "focus": "Save → Activate"
   }
  ]
 },
 {
  "key": "issues",
  "title": "Issue Follow-up & Remediation",
  "steps": [
   {
    "tab": "1 · Monitor issues",
    "title": "Monitor remediation across projects",
    "how": [
     "From Workspace Apps, open Issues & Actions.",
     "Open the Issues & Actions dashboard.",
     "Review issue and action visualizations; apply or reset filters as needed."
    ],
    "note": "This monitoring view is optional and available if Issues & Actions is enabled for your organization. Data comes from Projects.",
    "route": "activity",
    "focus": null
   },
   {
    "tab": "2 · Find an issue",
    "title": "Find the issue to follow up",
    "how": [
     "Open Issue Tracker to work across projects, or open one project and choose Issues.",
     "Search by issue title, filter, or sort the list.",
     "Click Details beside the issue."
    ],
    "note": "Use the Issues & Actions dashboard for monitoring; use Issue Tracker or Projects issue details to manage the finding.",
    "route": "issueTracker",
    "focus": "Details"
   },
   {
    "tab": "3 · Update remediation",
    "title": "Document management’s remediation plan",
    "how": [
     "On the issue detail page, open Follow-up & Remediation.",
     "Update overall status, remediation status, plan, deadline, and actual remediation date as appropriate.",
     "Click Save."
    ],
    "note": "Management response fields and who can edit them depend on assigned role. The page may be read-only for some roles.",
    "route": "issueRemediation",
    "focus": "Save"
   },
   {
    "tab": "4 · Add actions",
    "title": "Assign concrete remediation actions",
    "how": [
     "In Follow-up & Remediation, click Add next to Actions.",
     "Enter action title, owner, description, due date, optional priority and notification settings.",
     "Click Save; assigned owners receive notification according to settings."
    ],
    "note": "",
    "route": "issueActions",
    "focus": "Add"
   },
   {
    "tab": "5 · Owner follow-up",
    "title": "Action owner updates progress",
    "how": [
     "Open the assigned action from its notification link or navigate to the issue.",
     "Choose View/Discuss next to the action.",
     "On Action Follow-Up, update submitted date, status, comment, or attachment; click Save.",
     "When fully addressed, use Complete Action to record completion date and state."
    ],
    "note": "Action Follow-Up and Complete Action can remain editable after the Follow-up & Remediation section is signed off; the other action tabs may lock.",
    "route": "actionFollowUp",
    "focus": "Save"
   },
   {
    "tab": "6 · Retest",
    "title": "Auditor retests the control or process",
    "how": [
     "Open the issue and click Retest Information.",
     "Enter retest deadline/date and results overview.",
     "Attach supporting evidence if needed, then click Save.",
     "Record whether the issue is truly remediated and any new findings."
    ],
    "note": "",
    "route": "issueRetest",
    "focus": "Save"
   },
   {
    "tab": "7 · Verify & close",
    "title": "Confirm resolution before closing",
    "how": [
     "Review the action completion and remediation evidence.",
     "Document retest results and whether remediation resolved the finding.",
     "Route for required review/sign-off and update the issue’s configured status."
    ],
    "note": "Status names and closure rules are configurable. Do not mark an issue resolved until the required verification and review steps are complete.",
    "route": "issueSignoff",
    "focus": "Set and Notify Reviewer"
   },
   {
    "tab": "8 · Report status",
    "title": "Report outcomes and carry actions forward",
    "how": [
     "Review issue/action trends in Issues & Actions or Issue Tracker.",
     "Export accessible charts/tables if needed for follow-up reporting.",
     "Return to the Assurance Plan dashboard to see how status and risk coverage have changed."
    ],
    "note": "Issues & Actions issues and actions visuals are sourced from Projects; refresh if recent changes are not visible.",
    "route": "activityFollowUp",
    "focus": "Export"
   }
  ]
 },
 {
  "key": "strategy",
  "title": "Strategy: risk monitoring",
  "steps": [
   {
    "tab": "1 · Open Risk Manager",
    "title": "Risk Manager home: risk profile",
    "how": [
     "A Risk Manager administrator should configure access and the Strategy Map.",
     "Open Risk Manager.",
     "Use the risk profile to organize and monitor strategic risks."
    ],
    "note": "",
    "route": "riskProfile",
    "focus": "+ Add"
   },
   {
    "tab": "2 · Build risk profile",
    "title": "Build the organization’s risk profile",
    "how": [
     "Click Risk Library and select applicable risks, then click Import (#) Risks.",
     "Or click + Add, enter risk name and description, and click Save."
    ],
    "note": "Review industry risks first; add only risks that apply to your organization.",
    "route": "riskLibrary",
    "focus": "Import"
   },
   {
    "tab": "3 · Define risk details",
    "title": "Describe the risk and map its context",
    "how": [
     "Open the risk from Risk Profile.",
     "Click Details; complete configured fields and attributes.",
     "Save each field and return to the risk profile."
    ],
    "note": "",
    "route": "riskDetails",
    "focus": "Save changes"
   },
   {
    "tab": "4 · Assess inherent risk",
    "title": "Assess inherent risk across segments",
    "how": [
     "Open the risk and click Assessment.",
     "Select strategic objectives.",
     "For each operating segment, enter a score for each configured risk-scoring factor.",
     "Save the assessment."
    ],
    "note": "",
    "route": "riskAssessment",
    "focus": "Save"
   },
   {
    "tab": "5 · Visualize heatmaps",
    "title": "Visualize assessed risks",
    "how": [
     "Choose Heatmaps in the main navigation.",
     "Choose Strategy Heatmap or a Risk Heatmap.",
     "Review risk placement; move a risk to a different state when appropriate."
    ],
    "note": "",
    "route": "heatmaps",
    "focus": "Heatmap type"
   },
   {
    "tab": "6 · Link treatment objectives",
    "title": "Link the strategic risk to assurance objectives",
    "how": [
     "Open the strategic risk and click Treatment.",
     "Click Link Treatment.",
     "Search for a project/framework, expand it, select one or more objectives, and click Link # Treatments."
    ],
    "note": "Linking framework objectives commonly aggregates assurance across projects. Link a risk to either parent framework objectives or child project objectives, not both.",
    "route": "riskTreatment",
    "focus": "Link Treatment"
   },
   {
    "tab": "7 · Monitor metrics",
    "title": "Connect ongoing indicators (optional)",
    "how": [
     "Have metric data available in Results.",
     "Open the risk, click Metrics → Link Metrics, select metric(s), then Save and Done.",
     "Optionally configure an automated assessment driver and save."
    ],
    "note": "This step is optional and requires configured Results metrics and assessment criteria.",
    "route": "riskMetrics",
    "focus": "Link Metrics"
   },
   {
    "tab": "8 · Review assurance",
    "title": "Review aggregated assurance and residual risk",
    "how": [
     "Open the strategic risk and click Assurance.",
     "Review aggregated assurance, operational risk scores, control testing results, issue trends, and treatment areas.",
     "Click a treatment’s View link to return to its project/framework evidence."
    ],
    "note": "Assurance and testing data aggregate from linked project/framework objectives. Some issues will not roll up: issues must be created inside a linked objective and published.",
    "route": "riskAssurance",
    "focus": null
   },
   {
    "tab": "9 · Feed into planning",
    "title": "Feed risk insights into the next assurance cycle",
    "how": [
     "Use the risk assessment and linked project outcomes to identify gaps.",
     "Update the risk response or assurance treatment with the responsible team.",
     "Carry uncovered risks and control gaps into the next Assurance Plan."
    ],
    "note": "",
    "route": "planningFeedback",
    "focus": "Open Assurance Plans"
   }
  ]
 },
 {
  "key": "riskplanning",
  "title": "Risk-Based Assurance Planning",
  "steps": [
   {
    "tab": "1 · Identify gaps",
    "title": "Identify next-cycle planning priorities",
    "how": [
     "In Risk Manager, review risk assessments, heatmaps, and assurance outcomes.",
     "Flag high-priority risks without linked treatments, partial coverage, or open remediation.",
     "Agree priorities with the risk and audit owners before creating the plan."
    ],
    "note": "",
    "route": "riskProfile",
    "focus": null
   },
   {
    "tab": "2 · Review risk assurance",
    "title": "Check the evidence behind each gap",
    "how": [
     "Open the risk, then click Assurance.",
     "Review assurance, treatment areas, passing/failing/not-tested controls, and issue trends.",
     "Use the evidence to propose project objectives or further testing in the next plan."
    ],
    "note": "",
    "route": "riskAssurance",
    "focus": null
   },
   {
    "tab": "3 · Create next plan",
    "title": "Create the next annual assurance plan",
    "how": [
     "Open the Assurance Plans app.",
     "Click + Create plan.",
     "Use a clear name that identifies the period and plan scope."
    ],
    "note": "Only Project Admins, Project Creators, and Assurance Plans Admins can define plans. Plan creators should confirm project creation permissions too.",
    "route": "plans",
    "focus": "+ Create plan"
   },
   {
    "tab": "4 · Set period & capacity",
    "title": "Set the planning window and resource ceiling",
    "how": [
     "Enter the plan name and optional description.",
     "Set total available project hours and the planning-period start/end.",
     "Click Create plan."
    ],
    "note": "Dates should align with your organization’s fiscal year configuration.",
    "route": "planCreate",
    "focus": "Create plan"
   },
   {
    "tab": "5 · Add risk-linked work",
    "title": "Create a project around uncovered risk",
    "how": [
     "Click + Add to plan → Create a new project; enter project basics and Continue.",
     "Select relevant framework objectives—especially those linked to strategic risks—then Continue.",
     "Select applicable entities, review, then choose Create project."
    ],
    "note": "",
    "route": "planAdd",
    "focus": "Create a new project"
   },
   {
    "tab": "6 · Add existing projects",
    "title": "Reuse existing work where it still fits",
    "how": [
     "Link active projects to include work already underway.",
     "Rollforward project to reuse prior setup while entering new project details.",
     "Review retained content carefully, especially if prior project results are included."
    ],
    "note": "Up to 100 projects can be included in a plan. The user's role may limit create or rollforward actions.",
    "route": "planLink",
    "focus": "Continue"
   },
   {
    "tab": "7 · Check coverage & progress",
    "title": "Validate that the plan is balanced",
    "how": [
     "Review the plan’s Risks tab; confirm linked strategic risks are represented by framework-linked projects.",
     "Review Coverage by entity or category and look for gaps.",
     "Check project budgets against total resources and adjust scope as needed.",
     "Use the Activities tab later to review plan changes."
    ],
    "note": "",
    "route": "planOverview",
    "focus": "Open Risks tab"
   }
  ]
 }
];

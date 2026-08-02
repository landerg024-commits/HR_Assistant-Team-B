# AI HR Assistant

This is the base project foundation for the modular HR Assistant.

Included:
- Complete folder architecture
- Centralized settings and logging
- Reusable Streamlit UI shell
- Light and dark mode
- Placeholder pages

Not implemented yet:
- Database business logic
- Authentication
- Employee, policy, leave, request, and document workflows

## Run

```powershell
cd hr_assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```


## Foundation v1.1 update

- Sidebar is fixed on the left side.
- Sidebar width is locked to 285px.
- Sidebar collapse controls are hidden.
- Sidebar remains visible while the main content scrolls.


## Foundation v1.2 update

- Sidebar is forced to remain expanded.
- All known Streamlit collapse-button selectors are hidden.
- The main content keeps a permanent 285px sidebar offset.
- `initial_sidebar_state` is explicitly set to `expanded`.


## Foundation v1.3

- Fixed the CSS string formatting error caused by literal percentage symbols.
- Kept the sidebar permanently expanded.
- Added broader selectors for Streamlit sidebar controls.


## Database Architecture Module

This version adds:

- SQLAlchemy 2.x database layer
- SQLite development database
- PostgreSQL-compatible database URL configuration
- Flexible SQLAlchemy adapter
- Company, role, department, user, and employee models
- Company-based data isolation
- Repository pattern
- Employee-number uniqueness per company
- Duplicate employee full names are allowed
- Database creation and verification scripts

### Create the database

```powershell
python scripts\create_database.py
python scripts\check_database.py
pytest tests\test_database.py -v
```

Authentication and seed users are intentionally not included yet.


## Initial Data and Company Isolation Module

This version adds:

- Default company seed
- Five company-scoped system roles
- Initial company administrator
- Argon2 password hashing
- Initial admin employee profile
- Idempotent initial-data script
- Company-scoped user uniqueness
- Employee-number uniqueness per company
- Duplicate employee full names are allowed
- Initial-data verification and tests

### Configure the initial administrator

Copy `.env.example` values into `.env` and change:

```text
INITIAL_COMPANY_CODE
INITIAL_COMPANY_NAME
INITIAL_ADMIN_USERNAME
INITIAL_ADMIN_EMAIL
INITIAL_ADMIN_PASSWORD
INITIAL_ADMIN_EMPLOYEE_NUMBER
INITIAL_ADMIN_FIRST_NAME
INITIAL_ADMIN_LAST_NAME
```

The initial user is forced to change the password when login is implemented.

### Run

```powershell
python scripts\create_initial_data.py
python scripts\check_initial_data.py
pytest tests\test_password_manager.py tests\test_initial_data.py -v
```

Running `create_initial_data.py` repeatedly is safe and does not create duplicate records.


## v3.1 Commented Modules

This version keeps the same v3 behavior and adds:

- Expanded module docstrings
- Inline comments for important syntax and decisions
- Clear layer and data-flow explanations
- Debugging notes
- Comments for company isolation and duplicate-name handling
- Comments for password hashing and seed idempotency
- `DEVELOPER_GUIDE.md`


## v4 Authentication and Login

Implemented:

- Company-code login
- Username or email login
- Argon2 verification
- Active account validation
- Streamlit authentication session
- Admin and employee routing
- Protected layouts
- Logout
- Mandatory temporary-password replacement
- Light and dark mode on authentication pages
- Commented modules and debugging notes

Run:

```powershell
python scripts\check_initial_data.py
python scripts\check_authentication.py
pytest tests\test_authentication.py -v
streamlit run app.py
```


## v4.1 Light Mode Widget Contrast Fix

Fixed:

- Invisible text-input and password labels in light mode
- Dark input surfaces remaining active in light mode
- Low-contrast password visibility and help icons
- Low-contrast warning text
- Default red form-submit button replaced with the shared primary color
- Theme-aware form border and background

No authentication or database behavior was changed.


## v5 User and Employee Management

Implemented:
- Company-scoped Users page
- Company-scoped Employees page
- Employee onboarding
- Optional login-account creation
- Role, department, and manager selection support
- Account activation/deactivation
- Self-deactivation protection
- Duplicate full-name support
- Admin dashboard metrics
- Commented modules and automated tests

Run:
```powershell
pytest tests\test_admin_management.py -v
streamlit run app.py
```


## v5.1 Input Text Contrast Fix

Fixed:

- Light-mode input value text contrast
- Light-mode input background for current Streamlit BaseWeb DOM
- Password and text fields using both input and base-input wrappers
- Browser autofill contrast
- Nested primary-button text color

No database, authentication, user-management, or employee-management logic changed.


## v5.2 White Input Text in All Themes

UI-only fix:

- Input values remain white in light mode.
- Input values remain white in dark mode.
- Input backgrounds remain dark in both modes.
- Password, email, username, number, and autofilled fields are covered.
- Placeholder text remains lighter than entered values.
- No authentication, database, user, or employee-management logic changed.


## v5.3 Theme Loader f-string Fix

Fixed:

- NameError caused by unescaped CSS braces inside the Python f-string.
- White input text remains active in both light and dark modes.
- No authentication, database, Users, or Employees logic changed.


## v5.4 White Input Runtime Fix

UI-only changes:

- Removed the input text-shadow that caused outlined/ghost text.
- Added explicit focus and text-selection colors.
- Forced native dark input color scheme in both application themes.
- Added a zero-height MutationObserver fallback that applies white
  text directly to rendered Streamlit input elements.
- The script changes styles only and does not read or transmit values.
- Authentication, database, Users, and Employees logic are unchanged.


## v6 Organization Setup Management

Implemented:

- Company Profile page
- Company-name update with immutable company code
- Departments page
- Department creation and status management
- Roles page
- Custom role creation and status management
- System-role protection
- Assigned-role deactivation protection
- Company-scoped validation and tests
- Commented modules and updated developer guide

Run:

```powershell
pytest tests\test_organization_management.py -v
streamlit run app.py
```


## v6.1 Persistent Theme Selection

The selected theme remains active after form submissions, widget reruns,
browser refresh, logout/login, and new Streamlit sessions in the same
browser. Persistence uses session state, the URL theme parameter, and
browser localStorage.


## v6.6 Simple Default-Account Password Reset

This checkpoint removes the persistent browser authentication-token
experiment and returns to the simpler Streamlit session-state login flow.

Behavior:

1. A newly seeded default administrator starts with
   `must_change_password=True`.
2. After successful login, the password-change page opens immediately.
3. Admin and employee portals remain blocked until the password changes.
4. After a successful change, the flag becomes `False`.
5. Later logins proceed normally.
6. The seed does not force another reset for an existing account.

For an existing default administrator, require another reset with:

```powershell
python scripts\require_default_password_reset.py
python scripts\check_default_password_reset.py
```

The old `auth_sessions` table may remain in an existing SQLite database.
This simplified checkpoint does not use it.


## v6.7 Signed-Cookie Refresh Login

A full browser refresh now restores authentication without returning the
user to the login form.

Implementation:

- Streamlit session_state handles ordinary widget reruns.
- `st.context.cookies` reads the signed cookie synchronously on refresh.
- `streamlit-cookies-controller` writes and removes the cookie only during
  login, password change, and logout.
- `itsdangerous` signs and timestamps the cookie.
- No `auth_sessions` database table or migration is used.
- Password changes invalidate old cookies automatically.
- Inactive users, companies, or roles cannot restore authentication.
- The last employee/admin portal and page are stored in URL navigation
  parameters and restored only after authorization checks.

Production environment:

```env
AUTH_COOKIE_SECRET=replace-with-a-long-random-secret
AUTH_COOKIE_HOURS=12
AUTH_COOKIE_SECURE=true
```

For local `http://localhost`, keep `AUTH_COOKIE_SECURE=false`.


## v6.8 All Form Widget Contrast Fix

The login page text inputs were already forced to use a dark surface and
white value text in both themes. Employee and organization forms also use
date and select widgets, which required separate Streamlit/BaseWeb
selectors.

Fixed widgets:

- Text and password inputs
- Number inputs
- Date and time inputs
- Text areas
- Selectboxes and multiselects
- Dropdown option menus
- Date calendar popover

All listed widgets now use a consistent dark input surface with white value
text in both light and dark application modes.


## v6.9 Selectbox Value Contrast Fix

The date input was already fixed, but selectbox values such as
`No Department` and `No Manager` were still rendered using a nested
BaseWeb combobox element.

The theme now targets `data-baseweb="select"` directly and forces the
selected value, placeholder, combobox input, arrow, and dropdown options
to use white text on the shared dark input surface in both themes.


## v7.0 Refresh Login and Universal Form Contrast

Refresh login:

- The signed cookie is written first.
- The browser performs a real reload only after a short commit delay.
- Streamlit restores the user from the cookie on the next request.
- No auth-session database table or migration is used.
- Logout removes the cookie before returning to login.
- Password change replaces the signed cookie.

Universal form contrast:

- Text and password inputs
- Number inputs
- Date and time inputs
- Text areas
- Disabled values
- Selectbox and multiselect values
- Dropdown options
- Browser autofill

All listed controls use white values on the shared dark input surface in
both light and dark modes.


## v7.1 Employee-Only Flow Validation

A dedicated employee-only account flow is now tested.

Create a local sample employee:

```powershell
python scripts\create_sample_employee_account.py
python scripts\check_sample_employee_account.py
```

First-run test credentials:

```text
Company code: value of INITIAL_COMPANY_CODE
Username: employee.test
Temporary password: Employee123!
```

Expected behavior:

- Mandatory password change opens after first login.
- After changing the password, Employee Portal opens.
- No Admin Portal button is shown.
- Direct admin URL/query changes are redirected to Employee Portal.
- Admin layout independently rejects employee access.
- Browser refresh restores the employee role without elevating access.
- Admin and employee accounts remain separate database records.

The sample-account script is idempotent and does not reset an existing
employee password.


## v7.2 Login and Logout Transition Fix

Resolved:

- Login no longer remains indefinitely on `Completing sign in…`.
- Logout no longer leaves only the protected sidebar visible.
- The cookie component writes/removes the browser cookie first.
- A native one-second Streamlit fragment timer then reruns the full app.
- No sandboxed iframe top-level navigation is attempted.
- A logout-pending state blocks stale request-cookie restoration during the
  same Streamlit WebSocket session.

Expected:

```text
Sign In
→ Completing sign in…
→ Dashboard / Employee Portal

Log Out
→ Signing out…
→ Login page
```


## v8.0 HR Policy Q&A

Implemented:

- Company-scoped `hr_policies` table
- Draft, published, and archived policy statuses
- Versioned policy records
- Effective-date filtering
- Protected administrator Policies page
- Employee Company Policies browser
- Functional employee Policy Q&A chat
- Generic section and keyword matching
- Approved-policy source references
- Exact fallback:
  `Information not found in approved company policies.`
- Draft, archived, future-effective, and other-company policies are excluded
- Runtime creation of the missing `hr_policies` table
- Sample policy seed script

Local test setup:

```powershell
python scripts\create_sample_policies.py
streamlit run app.py
```

This module intentionally does not use a generative LLM or external
knowledge. Full document ingestion and advanced RAG remain future modules.


## v8.1 File-Based Policy Management

Policy source of truth is now the uploaded file.

Supported files:

- PDF
- DOCX
- TXT
- Markdown

Upload flow:

```text
Admin uploads policy file
→ file validation and SHA-256 calculation
→ private company-scoped storage
→ text and section extraction
→ draft or published policy record
→ employee Policy Q&A
→ direct answer with filename, section, and PDF page when available
```

Security and correctness:

- Maximum upload size is configurable.
- Unsupported file types are rejected.
- Filenames are sanitized before storage.
- Relative paths are checked against path traversal.
- Exact duplicate files are blocked within the same company.
- Draft, archived, future-effective, and other-company files are excluded.
- Employees download files only after company and publication checks.
- Scanned image-only PDFs are rejected because OCR is not enabled yet.
- Existing v8.0 manual policies remain readable for backward compatibility.

Configuration:

```env
POLICY_UPLOAD_DIR=data/uploads/policies
POLICY_UPLOAD_MAX_MB=10
```

Local sample:

```powershell
python scripts\create_sample_policies.py
```


## v8.2 Admin Policy Content Viewer

Administrators can now select an existing policy and inspect:

- Policy status, version, category, effective date, and summary
- Original filename, MIME type, file size, page count, and SHA-256
- Extracted policy content stored in the database
- The exact searchable sections used by Policy Q&A
- Optional PDF page number for each searchable section
- Original uploaded file download
- Complete extracted-text download
- Section heading/content search
- Publication-status management

Large extracted documents show the first 100,000 characters in the browser
and provide a complete plain-text download.

All content-view operations validate `company_id` through `PolicyService`.
Older v8.0 manual policy entries remain viewable.


## v8.2.1 Employee Onboarding Polish

The normal administrator Add Employee form now:

- Shows Role, Username, Login Email, and Temporary Password at all times
- Removes the optional login-account checkbox
- Creates the employee profile and linked login account together
- Defaults the role selector to `employee`
- Warns before assigning an elevated administrator role
- Requires a password change on first login
- Shows clear missing-field messages

The backend retains profile-only employee support for future imports,
integrations, and record-only workflows. It is not exposed in the standard
administrator onboarding form.


## v8.2.2 Secure Forgot Password

Self-service flow:

```text
Forgot Password
  ↓
Company Code + registered Login Email
  ↓
single-use reset link
  ↓
new password + confirmation
  ↓
old signed login cookies become invalid
```

Security:

- Existing passwords are never decrypted, displayed, or emailed.
- Database stores only a SHA-256 reset-token hash.
- Reset tokens expire after 30 minutes by default.
- Reset tokens are single-use.
- New reset requests revoke older active links.
- A per-account cooldown limits repeated emails.
- Public responses are generic to prevent account enumeration.
- Password changes invalidate signed-cookie password fingerprints.
- Open authenticated sessions are revalidated on the next Streamlit run.
- Company code and Login Email preserve tenant isolation.

Email modes:

```env
EMAIL_DELIVERY_MODE=local
```

Local development writes `.eml` files to:

```text
data/dev_mail_outbox
```

Read the latest local message with:

```powershell
python scripts\show_latest_password_reset_email.py
```

Production SMTP example:

```env
EMAIL_DELIVERY_MODE=smtp
PASSWORD_RESET_BASE_URL=https://hr.example.com
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=hr-system@example.com
SMTP_PASSWORD=your-app-password-or-smtp-password
SMTP_FROM_EMAIL=hr-system@example.com
SMTP_FROM_NAME=Company HR
SMTP_USE_STARTTLS=true
SMTP_USE_SSL=false
```

The `Users` administration page also includes an administrator-assisted
temporary-password reset for employees who cannot access their registered
Login Email. The employee must change that temporary password on next login.


## v8.2.3 Real SMTP Email Delivery

Forgot Password can now use real internet email through the configured SMTP
provider.

Configure SMTP interactively:

```powershell
python scripts\configure_smtp.py
```

The setup supports:

- Gmail / Google Workspace preset
- Microsoft 365 preset
- Custom SMTP host, port, and encryption

The private `.env` file receives the sender credentials. Existing values
are preserved and an `.env.backup` is created before updating an existing
file. The password is not printed by the setup script.

After configuration:

```powershell
Ctrl + C
streamlit cache clear
streamlit run app.py
```

Then open:

```text
Admin Portal → Integrations
```

The page safely displays:

- Delivery mode
- SMTP host and port
- Encryption
- Whether a username is configured
- Sender name/email
- Password-reset public URL

The SMTP password is never returned to the UI.

Use **Send Internet Test Email** before testing Forgot Password. A successful
test confirms that the app can reach the SMTP provider and authenticate with
the configured sender account.

Command-line test:

```powershell
python scripts\test_smtp_email.py recipient@example.com
```

The public Forgot Password page no longer displays local outbox paths or
development implementation details.


## v8.2.4 Email-Only Forgot Password

The employee Forgot Password form now asks for only:

```text
Registered Login Email
```

It no longer asks for Company Code.

Flow:

```text
Registered Login Email
  ↓
system finds active matching accounts
  ↓
single-use reset email
  ↓
new password
  ↓
sign in using the new password
```

Multi-company handling:

- Login Email remains company-scoped in normal account management.
- The same email may exist in more than one company.
- When that happens, each active matching account receives a separate email.
- Every message identifies the company and contains a token bound to only
  that company and user account.
- The public screen still returns the same generic response and does not
  reveal the number of matching accounts.

The SMTP provider remains a one-time private backend configuration. The
employee does not choose Gmail, Microsoft 365, a sender username, password,
or display name.


## v8.2.6 Employees Workspace Consolidation

The previous separate sidebar pages:

- Users
- Employees
- Roles

are now consolidated under one **Employees** navigation item.

Workspace tabs:

```text
Employees
  ├─ Employee Records
  ├─ User Accounts
  └─ Roles & Access
```

Responsibilities:

- **Employee Records** — employee list, onboarding, department/manager
  assignment, and linked account creation
- **User Accounts** — activation/deactivation and administrator-assisted
  temporary-password reset
- **Roles & Access** — system/custom role list, custom role creation, and
  custom-role activation status

Old bookmarks or query parameters for `Users` and `Roles` still open the
Employees workspace instead of failing.


## v8.3.0 Employee Master Record

The previous Employees workspace has been simplified to:

```text
Employees
  ├─ Employee List
  ├─ Add Employee
  └─ Edit Employee
```

Removed from the administrator UI:

- User Accounts tab
- Roles & Access tab
- Custom role assignment

Each employee record now contains:

```text
Employee Number
Last Name
First Name
Middle Name (optional)
Suffix (optional)
Job Title / Position
Department
Manager
Email
Status: Employed or Resigned
Training checklist
Account:
  User ID
  User Name
  Password reset field
  Clearance: 1 Admin or 2 User
```

Important security behavior:

- Actual passwords are never displayed or stored as plain text.
- The database stores only the Argon2 password hash.
- Editing the password uses a blank **New Temporary Password** field.
- A new temporary password forces password change during next login.
- Resigned employees remain in the database but their login account becomes
  inactive.
- Full Name is calculated from the separate name fields.
- Each training item is a separate database row, but the employee table
  displays the checklist in one combined cell.

Existing databases are upgraded automatically:

- Adds `users.clearance`
- Maps old administrator roles to clearance 1
- Maps other roles to clearance 2
- Converts active status to Employed
- Creates `employee_trainings`


## v8.3.1 Wrapped Employee Table

The Employee List no longer uses the default Streamlit dataframe renderer.

Every table cell now supports:

- automatic text wrapping
- preserved multiline Training checklist
- preserved multiline Account details
- top-aligned content
- long-email and long-word breaking
- sticky table header
- horizontal scrolling on smaller displays

Dynamic employee values are HTML-escaped before rendering.


## v8.3.2 Employment and Account Status Sync

```text
Employed -> Account Active
Resigned -> Account Inactive
```

The rule works in both directions. Returning a resigned employee to
Employed automatically reactivates the linked login account. Resigned
employee records remain stored for historical reference.


## v8.3.3 Consistent Administration Tables

The default Streamlit dataframe grid was replaced on administration pages
because its internal theme could remain dark while the surrounding app was
in Light Mode.

Updated tables:

- Employees
- Policies
- Policy details and original-file details
- Departments
- Integrations
- Legacy Users and Roles pages

All tables now provide:

- correct Light/Dark theme colors
- wrapped text in every cell
- multiline content support
- sticky headers
- horizontal scrolling on smaller screens
- HTML-escaped dynamic values
- CSS scoped to each table only


## v8.3.4 Department Entry Through Employees

The separate Departments sidebar item and active route have been removed.

```text
Employees
  ├─ Add Employee -> Department
  └─ Edit Employee -> Department
```

Existing department names are reused case-insensitively. New department names
create normalized database records automatically. The Department model,
table, repository, and employee relationship remain for filtering, reports,
and future integrations. Old Departments bookmarks redirect to Employees.


## v8.3.5 Safe Employee Delete

A permanent-delete option is available under:

```text
Employees -> Edit Employee -> Danger Zone
```

The admin must type the exact Employee Number and acknowledge the permanent
action. The signed-in administrator cannot delete their own account.
Employees referenced by policy history cannot be deleted and should be set
to Resigned instead.

Deletion removes the employee profile, training records, linked login
account, and password-reset tokens. Department records and direct-report
employees remain. Direct reports are changed to No Manager.


## v8.3.6 Employee Operation Feedback

Employee operations now show a visible loading indicator:

```text
Add Employee    -> Creating employee record and login account…
Edit Employee   -> Saving employee changes…
Delete Employee -> Permanently deleting employee record…
```

After completion, the result is stored in Streamlit session state before
`st.rerun()`. The refreshed Employees page displays both:

- a persistent success banner
- a short success toast

Validation and database errors remain visible in the active form and do not
show a false success message.


## v8.3.7 Hover Style Restore

Hover styling is restored without changing employee business logic.

Updated:

- normal and sidebar buttons
- primary/form-submit buttons
- page tabs
- expanders, including the Delete Danger Zone
- Employees table rows
- reusable administration table rows

The hover uses the shared `primary_soft` token, so Light Mode receives a
soft blue-violet background and Dark Mode receives the matching dark accent.
No transform, movement, or layout shift is applied.


## v8.3.10 Light Mode Only

The application now uses one fixed Light Mode and no theme selector.

Light form controls:

- white input/select/textarea background
- dark readable values
- muted gray placeholder text
- soft gray-blue hover border
- violet focus border
- white dropdown/calendar surfaces
- soft blue-violet option hover

Preserved from v8.3.7:

- sidebar and page layout
- wrapped administration tables
- button, tab, expander, and row hover behavior
- employee add/edit/delete behavior
- loading indicators
- success banners and toasts
- authentication and database logic

No native `.streamlit/config.toml` override was introduced.


## v8.3.11 Light Mode Text Contrast Fix

Text color now follows the actual UI surface:

```text
White/light surface       -> dark text
Violet/primary surface    -> white text
Soft-violet hover surface -> violet text
Disabled light field      -> readable muted text
```

The patch also forces Streamlit/BaseWeb input and select wrappers to remain
white whenever their value text is dark. This prevents black text from
appearing on a retained dark native control background.

No employee, authentication, loading, database, table-layout, or navigation
logic was changed.


## v8.3.12 Light Page with Dark Inputs

The page remains Light Mode while editable controls use the approved dark
surface.

```text
Page/cards/sidebar  -> Light
Input box           -> Dark (#252630)
Typed value         -> White
Placeholder         -> Muted light gray
Input hover         -> Slightly lighter dark
Input focus         -> Violet border
Dropdown            -> Dark with white text
```

Labels remain dark because they are outside the input and displayed on the
light page. No employee, authentication, loading, table, or database logic
was changed.


## v8.3.13 Native Control Hover

Added scoped hover styling for Streamlit controls that do not inherit the
normal button/input hover rules:

- file-uploader dropzone
- Upload/Browse button
- uploaded-file row
- remove-file button
- checkbox label and indicator

The page remains Light Mode while form controls remain dark with white text.
No policy upload logic, employee logic, database logic, or layout changed.


## v8.3.14 Tooltip Contrast Fix

Streamlit help tooltips now use:

```text
Tooltip surface -> dark
Tooltip text    -> white
Tooltip icon    -> readable gray
Icon hover      -> soft violet
```

CSS and a small MutationObserver fallback both cover tooltips created after
the initial Streamlit render. Existing file-uploader hover, Light Mode page,
dark controls, white input values, and application logic are unchanged.


## v8.3.15 Download Action Contrast

The three active download actions now have explicit states:

```text
Normal   -> white surface, dark text
Hover    -> violet surface, white text
Focus    -> violet surface, white text, focus ring
Active   -> darker violet
Disabled -> light gray surface, readable muted text
```

The visual audit also rechecked ordinary buttons, form-submit buttons,
file uploaders, tooltips, checkboxes, inputs, tabs, and tables. No policy,
employee, authentication, or database logic changed.


## v8.4.0 Policy Library Redesign

- User-facing IDs use `PID_001` format.
- The active table shows Filename/Title, Category, Version, File Size, and Date Uploaded.
- Filename-derived title and heading-derived category suggestions are automatic.
- Category remains editable and is used for filtering and Q&A organization.
- Version stays manual while previous versions remain visible.
- Upload preview is integrated into the upload section.
- Every successful upload is immediately published.
- Policies can be moved to a reversible Bin and restored; no permanent delete exists.
- Both filename auto-detection and explicit existing-policy selection link new versions.


## v8.4.1 Expander Contrast Fix

The Document Preview header is now readable before hover.

```text
Normal   -> white surface, dark text
Hover    -> soft violet surface, violet text
Focused  -> soft violet surface, visible focus treatment
Expanded -> pale violet surface, violet text
Arrow    -> readable gray/violet
```

The same styling applies consistently to other Streamlit expanders.
Policy preview content, upload processing, version linking, Bin behavior,
employee logic, authentication, and database logic are unchanged.


## v8.4.2 Toast Contrast Fix

Success toasts now use a complete dark-surface contrast system:

```text
Toast surface -> dark
Message text  -> white
Success icon  -> bright green
Close icon    -> light gray
Toast hover   -> slightly lighter dark
```

CSS and the existing MutationObserver runtime fallback cover notifications
created after a Streamlit rerun. The page success banner, policy Bin action,
upload flow, tables, employee features, authentication, and database logic
are unchanged.


## v8.4.3 Policy Upload Reset

After a successful policy upload, the entire upload workspace resets:

```text
successful database/file transaction
  ↓
advance upload-widget generation
  ↓
Streamlit rerun
  ↓
empty file uploader
  ↓
title/category/version/preview/history controls hidden
```

The reset covers:

- selected policy file
- version-linking choice
- selected existing policy
- suggested/edited category
- manual version value
- previous-version table
- extracted document preview
- upload submit state

Validation, parsing, duplicate-version, or database errors do not reset the
form, allowing the administrator to correct the current upload. The success
banner and toast remain visible after the rerun.


## v8.4.4 Policy Edit, New Version, and Permanent Delete

### Manage Existing Policy

New actions:

```text
Edit Details
Upload New Version
Move to Bin
```

- Policy Title and Category are applied to all versions in the same policy
  family so version history remains grouped.
- Version changes only the selected record.
- Editing metadata never overwrites the original uploaded file or extracted
  content.
- Upload New Version creates a separate published record and preserves all
  earlier active or Bin versions.

### Bin

New protected action:

```text
Delete Permanently
```

The administrator must type the exact Policy ID and acknowledge permanent
deletion. The operation removes only the selected Bin version:

- policy database row
- original stored file
- uploaded-document metadata
- extracted full text
- searchable sections

Other versions of the same policy remain available. Active policies cannot
be permanently deleted; they must be moved to the Bin first.


## v8.4.5 Policy Content Edit and Readable Preview

### Edit Details

The selected version now includes editable Policy Content. Saving it updates:

- policy database content
- extracted-content viewer
- generated summary
- stored extracted text
- searchable sections used by Policy Q&A

The original uploaded file, hash, filename, and storage path remain unchanged.
Regenerated sections no longer retain page numbers because edited content may
not match the original source pages exactly.

### Upload Preview

Detected headings are displayed as a wrapped vertical numbered list.

Extracted content is displayed in a section-by-section stacked preview:

```text
1. Section Heading
────────────────────────────────
Section content

2. Next Heading
────────────────────────────────
Next section content
```

The layout is shared by the main Upload Policy flow and Upload New Version.


## v8.4.6 Full Policy Content View

Policy content is no longer limited in the administrator interface.

### Edit Details

- The complete editable content is loaded.
- Editor height expands according to all content lines.
- No internal fixed-height content limit is used.
- Line height is reduced to `1.30` for a compact but readable layout.

### Upload and New-Version Preview

- Every unique detected heading is displayed.
- The `+ more detected sections` message is removed.
- Every extracted section and its full text are displayed.
- Character and section preview limits are removed.
- Section gaps and list spacing are reduced.
- The complete preview remains inside the collapsible Document Preview area.

No policy extraction, save, versioning, Bin, employee, authentication, or
database behavior changed.


## v8.4.7 Policy Section Heading and Content Layout

Each preview section now follows:

```text
────────────────────────────────
Topic / Heading
Content
────────────────────────────────
Next Topic / Heading
Content
────────────────────────────────
```

The separator is no longer between a heading and its own content. Heading
and body are rendered inside one scoped HTML section.

Source text is escaped and newlines are converted to explicit HTML breaks,
preventing the last part of long documents from leaving the dark preview
surface and inheriting black Light Mode text. All nested heading and body
text is forced to white.

The complete unlimited preview remains enabled.


## v8.5.0 Leave Management

### Administration Portal

The former **Leave Settings** navigation item is now **Leave Management**.
It contains:

- Leave Overview
- Leave Credits per employee
- Manual credit adjustments and credit history
- Leave Requests for monitoring and View Details only
- Leave Types & Rules

There are no Admin approve, reject, or cancel actions. Requests are sent to
the employee's assigned department manager. The employee and active company
administrators are copied on the email.

### Employee Portal

Employees can:

- review annual, carried, adjusted, used, reserved, and remaining credits
- submit Vacation, Sick, Emergency, or configured leave requests
- attach PDF, DOCX, PNG, JPG, or JPEG supporting documents
- see their sent request history

Submitting a request reserves available credits, records the request, creates
in-app notifications, and sends an email to the assigned manager. Approval is
handled through the department process outside the HR Admin portal.

### Notification Bell

The authenticated top bar now includes a bell with unread count, recent
notifications, and a **Mark All as Read** action.

New database tables are created automatically and non-destructively:

- `leave_types`
- `leave_balances`
- `leave_credit_transactions`
- `leave_requests`
- `notifications`


## v8.5.1 Company Theme Color

Company Profile now includes a company-wide Primary Accent Color picker.

```text
Default color       -> violet (#4338E8)
Selected color      -> stored per company
Primary buttons     -> selected color
Hover state         -> automatically derived
Soft accent         -> automatically derived
Text on accent      -> automatically black or white for contrast
```

The saved color is used in both Administration and Employee portals for:

- active sidebar navigation
- primary and submit buttons
- tab accents
- focus borders and rings
- checkbox and selection states
- notification bell hover
- uploader and download actions
- branding and soft hover surfaces

The color is stored in `companies.theme_primary_color`. Existing databases
receive the column non-destructively and keep the default violet color.

Company Profile provides:

- live Primary, Hover, and Soft Accent preview
- Save Theme Color
- Reset to Default Violet

Light Mode remains fixed. Dark input surfaces, white input values, Leave
Management, policy features, authentication, and business logic are
unchanged.


## v8.5.2 Leave Detached-Instance Fix

Leave Management repository queries now eagerly load every relationship used
after the database session closes.

Covered relationships:

- Leave Balance → Employee
- Leave Balance → Employee Department
- Leave Balance → Employee Manager
- Leave Balance → Employee/Manager User Account
- Leave Balance → Leave Type
- Leave Request → Employee Department
- Leave Request → Employee/Manager User Account
- Leave Request → Leave Type

This prevents SQLAlchemy `DetachedInstanceError` when Streamlit renders leave
credits or request details after leaving the `SessionFactory()` context.

No database migration is required. Leave calculations, email routing,
notifications, company theme colors, policies, authentication, and employee
records are unchanged.


## v8.5.3 Leave Workspace Reorganization

The administrator Leave Management workspace is reorganized into:

```text
Leave Overview
Credit Management
Leave Requests
Leave Types & Rules
```

### Shared Leave Year

The Leave Year selector is displayed once above the tabs and controls:

- Leave Overview balances and metrics
- Credit Management adjustments and history
- Leave Requests whose leave dates overlap the selected year

Requests crossing December and January appear in both affected leave years.

### Leave Overview

Read-only information is consolidated here:

- selected-year summary metrics
- employee leave-credit table
- View Employee Credit Details
- allocated, carry-over, adjustments, used, reserved, and remaining credits

### Credit Management

Only administrative credit actions are shown here:

- employee selector
- manual positive or negative credit adjustment
- required adjustment reason
- immutable credit transaction history

The old `Leave Credits` tab name is removed to avoid duplicating viewing and
management functions.

Manager-routed request approval remains outside the HR Admin portal. Company
theme colors, notifications, policies, authentication, email routing, and
database records remain unchanged.


## v8.5.4 Simplified Leave Management

The administrator workspace is simplified into four clear areas:

```text
Overview
Employee Leave Accounts
Leave Requests
Leave Rules
```

### Overview

Overview is now a true monitoring dashboard and does not repeat the complete
employee credit table or adjustment forms.

It contains:

- selected-year request metrics
- employees currently on leave
- selected-year leave activity
- low-credit alerts
- recent leave requests

### Employee Leave Accounts

All employee-specific credit work is consolidated in one place:

- department filter
- employee selector
- available, used, and reserved totals
- complete leave-type credit breakdown
- manual positive or negative adjustment
- immutable transaction history

This removes the previous separation between credit viewing and credit
management.

### Leave Requests

Requests remain view-only for HR/Admin and include:

- department filter
- leave-type filter
- status filter
- employee-name or employee-number search
- request table
- complete request details and attachment download

Department managers remain responsible for approving or rejecting requests
outside the HR Admin portal.

### Leave Rules

Leave type configuration is renamed and simplified:

- Add Leave Rule
- Edit Leave Rule
- Save Leave Rule
- annual credits
- paid/unpaid
- carry-over limit
- attachment requirement
- minimum notice
- active/inactive

One shared Leave Year continues to control Overview, Employee Leave Accounts,
and Leave Requests. No database migration is required.


## v8.5.5 Absolute Leave Credits

Employee Leave Accounts no longer uses positive or negative adjustment
numbers.

The administrator now enters the exact remaining credits:

```text
Current credits: 45
New Leave Credits: 10
Saved result: 10
```

The value is not added to the current balance.

### Updated interface

- `Adjust Credits` is renamed to `Set Leave Credits`
- `Adjustment Days` is replaced by `New Leave Credits`
- minimum input value is zero
- the current balance is the default input value
- `Save Leave Credits` clearly saves the exact resulting amount
- the help text includes a 45-to-10 example
- internal signed adjustment arithmetic is hidden from the employee balance
  table
- transaction history records the previous and new balance plus the reason

The service recalculates its internal adjustment component while preserving
annual allocation, carry-over, used days, reserved days, and leave-request
history. No database migration is required.


## v8.5.6 Remove Leave-Credit Reason

The manual reason field is removed from Employee Leave Accounts.

The `Set Leave Credits` form now contains only:

```text
Leave Type
Current Credits
New Leave Credits
Save Leave Credits
```

Transaction history still records:

- previous balance
- new balance
- administrator user reference
- date and time of the change

No user-entered adjustment reason is requested or displayed. No database
migration is required.


## v8.6.0 Manager Approval and Leave Credit Posting

### Employee Portal

Leave Management now contains:

```text
My Leave Overview
File Leave Request
My Requests
Pending Approvals       # assigned managers only
Reviewed Requests       # assigned managers only
```

The request composer shows:

- Leave Type and current available credits
- Start Date and End Date
- calculated Monday-to-Friday Working Days
- Reason
- Work Handover Plan / Countermeasure
- optional PDF, DOCX, XLSX, CSV, or TXT plan file
- automatic To: assigned manager
- automatic CC: employee and active administrators

### Handover Plan Rules

Leave Rules supports:

```text
Optional
Recommended
Required
```

A Required rule accepts either plan text or an uploaded plan file. Vacation
and Leave Without Pay default to Recommended. Sick and Emergency default to
Optional because they may be unexpected.

### Manager Approval

The assigned manager receives:

- an in-app bell notification
- an email containing the request and handover plan
- a login-protected link to Employee Portal Leave Management

Managers can approve or reject only requests assigned to their employee
record. HR/Admin remains view-only.

### Credit Lifecycle

```text
Pending Manager Approval
    No reservation and no deduction

Approved / Scheduled
    Requested days become Reserved
    Available Credits decreases

Approved leave date occurs
    Date reconciliation moves elapsed days from Reserved to Used

All approved leave dates completed
    Status becomes Completed
```

Rejected requests never affect credits.

### Date Reconciliation

Two safeguards are included:

1. Streamlit runs reconciliation whenever an authenticated user opens the app.
2. `python scripts/reconcile_leave_credits.py` can be scheduled daily through
   Windows Task Scheduler.

Posting is idempotent. A date already posted cannot be posted twice.

### Compatibility

Existing v8.5.x `sent_to_manager` requests are converted to Pending Manager
Approval during the non-destructive schema upgrade. Their old submission-time
reservations are released. No database reset is required.


## v8.6.1 Global Notification UI

The top-bar bell is a global notification center, not a leave-only feature.

### Readability

The popover now uses:

- a fixed white notification surface
- dark high-contrast heading, title, message, and timestamp text
- compact notification cards
- unread soft-accent background and dot
- a readable empty state
- a clear unread count
- a compact bell button
- responsive width and scrollable recent-notification list

### Generic categories

The UI automatically labels notification events as:

```text
Leave
Policy
Training
Employee
Security
System
General
```

The notification model and service remain generic and company/user scoped.
Leave is currently the first fully connected workflow. Policy, training,
employee/account, security, and other modules can publish events through the
same `NotificationService.create(...)` method as those workflows are wired.

No database migration is required.


## v8.6.2 Notification Trigger and Render Fix

This UI patch fixes three notification-center problems:

1. The bell no longer changes to an unreadable black or mismatched state.
2. The bell and arrow remain visible during normal, hover, focus, click, and
   open states.
3. `Mark All as Read` no longer exposes raw HTML tags.

### Bell states

```text
Normal
White surface
Dark visible bell and arrow

Hover / Focus / Open
Soft company accent surface
Dark visible bell and arrow
Company accent border
```

### Notification rendering

All recent notification cards are joined into one contiguous HTML block before
being passed to Streamlit. This prevents Markdown from interpreting indented
HTML as a code block during the read-state rerun.

The notification center remains system-wide. No database migration is
required.


## v8.6.3 Public Company Branding

The saved company Primary Accent Color now applies before and after login.

### Covered pages

```text
Login
Forgot Password
Reset Password
Mandatory First Password Change
Administration Portal
Employee Portal
```

### Login behavior

- The Company Code field is outside the credential form so it can refresh
  public branding without submitting a username or password.
- Entering a valid company code updates the login accent and preserves the
  code in the browser URL/session.
- A single-company installation automatically uses its saved company color.
- A multi-company installation uses the matched company code.
- Logout preserves the current company code so the user returns to the same
  branded login page.

### Password reset

Reset links now include the company code. A valid reset token can also resolve
its company directly, so the Reset Password page uses the correct company
name and accent even when opened in a new browser.

The Forgot Password form remains email-only and does not ask for company code.

No database migration is required.


## v8.7.0 Announcements and Employee Dashboard

### Admin Portal — Announcements

Administrators can publish proper company communications with:

```text
Announcement Title
Category
Short Summary
Full Announcement
Optional Cover Image
Publish Date
Optional Expiry Date
Pin on Employee Dashboard
Save as Draft
Publish / Schedule
```

Supported categories:

```text
Company Announcement
Company Activity
Event
Reminder
HR Update
Policy Update
Emergency Notice
```

Cover images support JPG, JPEG, PNG, and WEBP up to the configured
`ANNOUNCEMENT_UPLOAD_MAX_MB` limit.

The module includes:

- lifecycle metrics
- complete announcement table
- employee-view preview
- draft creation
- scheduled publishing
- editing and image replacement
- archive and restore-to-draft
- pinned announcements
- automatic employee notifications

### Employee Portal — Dashboard First

`Dashboard` is now the first employee navigation item and the default page
after employee login or when an administrator switches to Employee Portal.

The dashboard contains:

- featured pinned announcement
- latest company updates
- recent company activities and notices
- full announcement expanders
- View All Company Announcements
- quick access to Leave Management, Company Policies, and HR Assistant

A searchable `Company Announcements` page provides the complete active archive.

### Dissemination

When a post becomes active, every active company user except the publishing
administrator receives an in-app global notification. Scheduled announcements
are reconciled whenever the app opens and through:

```powershell
python scripts/reconcile_announcements.py
```

Expired posts automatically disappear from the Employee Portal while
remaining available to administrators.

### Storage and database

Announcement images are stored privately under:

```text
data/uploads/announcements/
```

The new announcement table is created automatically without resetting the
existing database.


## v8.7.1 Notification Theme Contrast

The notification bell and unread number now follow the saved company Primary
Accent Color in normal, hover, focus, active, and open states. The text color
uses the automatically calculated `--hr-on-primary` contrast value, so light
company colors use dark text and dark company colors use white text. The unread
count inside the notification panel follows the same branding. No database
migration is required.


## v8.7.2 Notification Unread Company Theme

The notification button now has two deliberate visual states:

```text
No unread notification
- white button
- company-color bell and arrow
- subtle company-color border

Unread notification
- full company primary-color button
- automatic accessible black/white icon and count
- visible focus ring
```

The button renders an explicit unread/empty state marker so CSS does not need
to guess from the visible label. This also supports Streamlit DOM variants
through a fallback selector.

The company theme applies to the normal, hover, focus, active, and open states.
No database migration is required.


## v8.7.3 Notification Direct Company Theme

The notification button is now placed inside a keyed Streamlit container:

```text
notification_bell_container
```

This gives the theme a stable selector and avoids relying on Streamlit's
changing sibling/wrapper structure.

The notification button now always uses:

```text
Background: Company Primary Accent Color
Bell / Unread Number / Arrow: Automatic Accessible Contrast
Hover / Focus / Open: Company-color responsive state
```

This applies whether the unread count is zero or greater than zero. The
button no longer falls back to the dark form-control color.

No database migration is required.


## v8.7.4 Notification Default Visibility

The notification button is readable before hover:

```text
Default
- white background
- company-color bell
- company-color unread number
- company-color arrow

Hover / Focus / Open
- soft company-color background
- bell, unread number, and arrow remain visible
```

A browser-side MutationObserver locates the actual Streamlit popover button by
its bell label and reapplies inline `!important` styles after every rerender.
This prevents later dark BaseWeb button styles from hiding the unread count.

No database migration is required.


## v8.7.5 Notification, Announcement Archive, and Merged Dashboard

### Notification

The notification indicator no longer uses `st.popover`.

```text
Default state
- company primary-color button
- visible bell
- visible unread count, including zero
- no hover required

Click
- opens a Notifications dialog
- recent notification cards
- Mark All as Read
```

### Announcement Delete

`Delete Announcement` is a soft-delete action:

```text
Delete Announcement
→ Status becomes Archived
→ Removed from Employee Dashboard
→ Record and image remain stored
→ Can be restored as Draft
```

The Admin Portal includes a dedicated Archive tab.

### Employee Portal

Dashboard and Company Announcements are merged into one page.

```text
Main wide area
- category filter
- announcement search
- featured pinned announcements
- latest active announcements

Compact right column
- Leave Management
- Company Policies
- HR Assistant
```

The separate Company Announcements sidebar item is removed. Old saved URLs are
automatically rendered through Dashboard.

No database migration is required.


## v8.7.6 Notification Dropdown and Responsive Announcement Images

### Notification location

The notification center is no longer a centered dialog.

```text
Click company-colored bell
→ Dropdown appears directly below the bell
→ Recent notifications
→ Mark All as Read
→ Close
```

The unread count remains visible in the default state.

### Announcement images

Admin and Employee announcement images now use a shared aspect-ratio-safe
renderer.

```text
- never stretched
- never distorted
- never enlarged beyond the original size
- automatically reduced to fit maximum width and height
- EXIF orientation corrected
- centered inside the available announcement area
```

Large, wide, tall, and small uploaded images retain their natural proportions.

No database migration is required.


## v8.7.7 Clickable Notifications and Title-First Announcements

### Announcement layout

The announcement information now appears before the image:

```text
Category and publish date
Announcement title
Short summary
Pinned status
Responsive image
Full announcement
```

This applies to Admin previews and the Employee Dashboard. Images continue to
preserve their natural aspect ratio without stretching.

### Wider notification dropdown

The panel is now up to 460 pixels wide and is positioned beneath the bell using
the bell button's actual browser coordinates. Text wraps normally instead of
collapsing into a narrow vertical column.

### Clickable notifications

Every recent notification is a clickable card. Opening one:

```text
- marks that notification as read
- closes the dropdown
- navigates to the related module
- preserves the related entity ID in the URL when available
```

Routing includes Announcements, Leave Management, Policies, Employees,
Integrations, Company Profile, Onboarding, and the appropriate dashboard.

No database migration is required.


## v8.7.8 Full-Width Employee Announcements

The redundant Quick Access panel is removed from the Employee Dashboard.
Leave Management, Company Policies, and HR Assistant remain available in the
fixed employee sidebar.

The dashboard now uses the available content width for company announcements,
filters, search, featured posts, and latest updates. Notification deep links
remain supported.

No database migration is required.

## v8.8.0 Context-Aware HR Assistant

The Employee Chat Assistant is no longer policy-only.

### Grounded answer sources

```text
Live employee master record
Live leave credits
Live leave request history
Configured leave types and operational rules
Approved published company policy files
Existing HR application modules
```

The assistant does not use outside knowledge and does not invent unavailable
company information.

### Leave shorthand and context

```text
VL = Vacation Leave
SL = Sick Leave
EL = Emergency Leave
LWOP = Leave Without Pay
```

Configured custom leave codes and names are matched dynamically. Short
follow-up questions reuse the previous user topic:

```text
User: Paano mag-file ng VL?
User: Ilan na lang?
Assistant: Returns the signed-in employee's current VL breakdown.
```

### Clickable navigation

Answers can open Leave Management, File Leave Request, My Requests, Company
Policies, My Documents, Benefits, Onboarding, HR Contacts, FAQ, and Dashboard.
Leave-related actions support direct views through the `leave_view` query
parameter.

No database migration is required.


## v8.8.1 Readable HR Assistant Responses

The invisible white Markdown list text in the HR Assistant is fixed.

Messages now use a stable keyed wrapper and `st.markdown`, preserving:

```text
Bullets
Numbered steps
Bold leave codes
Links
Policy formatting
```

A Light Mode contrast guard also covers read-only list content in policy
sections, expanders, alerts, and other HR information. Dark editable form
controls remain unchanged.

No database migration is required.


## v8.8.2 Readable Policy Content

Employee policy source text no longer uses the `st.text` component that
inherited an invisible white foreground in Light Mode.

The policy browser now:

```text
Escapes uploaded source text safely
Preserves original line breaks
Uses normal readable typography
Wraps long paragraphs
Keeps headings, numbered paragraphs, and lists visible
```

The Policy Assistant answer is also rendered through a stable keyed Markdown
wrapper. A fallback covers read-only `st.text` and preformatted content inside
policy expanders without changing dark editable form fields.

No database migration is required.


## v8.8.3 Private and Topic-Aware HR Chat

### Conversation privacy

HR Assistant state is scoped using both `company_id` and `user_id`.
Messages, input text, action widgets, and New Conversation controls are
account-specific.

Legacy global chat state is deleted rather than assigned to a newly logged-in
employee. Private chat state is cleared when the authenticated account changes,
logs out, or is cleared after an external password reset.

### Topic reset

A short message is no longer automatically treated as a follow-up.

```text
Leave
→ Leave topic

Policy
→ New policy topic
```

Conversation history is used only for explicit incomplete follow-ups such as:

```text
Ilan na lang?
How many left?
Paano naman?
What about that?
```

Recognizable standalone topics always take priority over previous messages.

No database migration is required.


## v8.8.4 Admin HR Assistant

The Administration Portal now includes a private, company-scoped Chat
Assistant. Its conversation is separate from the Employee Portal chat, even
when the same administrator switches between portals.

### Administrator questions

```text
How many employees do we have?
Show active and inactive user accounts.
Are there pending leave requests?
Show the leave credits of EMP-001.
How many policies are published?
What is the company policy on overtime?
How many announcements are scheduled?
How do I create an announcement?
Where do I configure SMTP?
```

The assistant uses live company records, approved policy sections, and safe
navigation actions. Personal employee questions from an administrator—such as
"Ilan na lang leave ko?"—still use the signed-in administrator's own employee
record.

### Security and privacy

```text
Company-scoped using company_id
Private state using company_id + user_id
Separate Admin and Employee Portal conversations
Cleared on account change, logout, and password-reset session clear
No password hashes, reset tokens, SMTP passwords, or cookie secrets displayed
```

No database migration is required.


## v8.8.5 Company Logo Branding

Administrators can upload, replace, preview, or remove a company logo from:

```text
Admin Portal -> Company Profile -> Company Logo
```

Supported uploads:

```text
PNG
JPG / JPEG
WEBP
Maximum size: configurable, 5 MB by default
```

Uploaded images are decoded, validated, resized only when necessary, and
re-encoded as a safe canonical PNG. The image remains company-scoped at:

```text
data/uploads/company_logos/<company_id>/company_logo.png
```

The logo is displayed at the top of both fixed protected sidebars:

```text
Admin Portal sidebar
Employee Portal sidebar
```

CSS uses `object-fit: contain`, centered alignment, bounded width and height,
and automatic dimensions so wide or tall logos are never stretched or cropped.
When no logo is configured, the sidebar shows a neutral Company Logo
placeholder.

Existing databases receive the nullable `companies.logo_filename` column
through the additive runtime schema upgrade. No destructive migration is used.


## v8.8.6 Larger Company Logo

The company logo now uses nearly the full sidebar logo holder.

```text
Holder height: 112 px
Logo maximum height: 104 px
Inner padding: 4 px vertical / 5 px horizontal
Width and height: use the available holder area
Scaling: object-fit contain
Alignment: centered
```

The logo remains proportional and is not cropped or stretched. The same
company-scoped logo continues to appear in both Admin and Employee portals.

No database migration is required.


## v8.8.8 Specific Notification Deep Links

Notification clicks now open the exact related record instead of only the parent module.

For leave notifications:

```text
Admin notification → Leave Requests → specific request details
Employee notification → My Requests → specific request details
Manager pending notification → Pending Approvals → specific request
Manager decision notification → Reviewed Requests → specific request
```

The route uses both `leave_request_id` and `leave_view`. The destination validates the signed-in employee or manager context before showing employee-portal details. No database migration is required.


## v8.8.9 Employee Form and Searchable List

The Add Employee and Edit Employee tabs now use the same card-based layout:

```text
Employee Information
Name fields
Employment and organization fields
Training Checklist

Account Information
User ID and clearance
Username and temporary password
```

The Employee List now includes a company-scoped search field. All matching
records remain in the table, while the viewport shows five fixed-height rows.
Visible vertical and horizontal scrollbars provide access to the remaining
records and columns. Search covers employee number, name, email, department,
manager, job title, username, account state, status, and training items.

No database migration is required.


## v8.8.10 Notification Tab Targeting

Leave notification links now keep the complete Leave Management workspace and
select the exact tab plus the related request. Admin notifications open the
Leave Requests tab and select the matching request in View Request Details.
Employee and manager notifications select My Requests, Pending Approvals, or
Reviewed Requests as appropriate. No database migration is required.


## v8.8.11 Refresh-Safe Authentication

Normal browser refreshes now preserve the signed-in account and current
Admin or Employee Portal route. The authentication flow checks both the
initial Streamlit request cookies and a one-cycle browser-component fallback
before showing the login page.

When `AUTH_COOKIE_SECRET` is blank, the application creates a private local
secret at `data/.auth_cookie_secret`. Preserve this file with the `data`
folder so valid sessions also survive Streamlit server restarts. Explicit
logout, password reset, expired cookies, disabled accounts, and password
changes still invalidate authentication.

No database migration is required.


## v8.8.12 Admin and Employee UX Refinements

- Ctrl/Cmd+C now remains the normal browser Copy shortcut and no longer
  opens Streamlit's Clear Caches dialog.
- Admin HR Assistant uses admin-specific Quick Actions matching the card
  organization of the Employee HR Assistant. The redundant Admin Shortcuts
  and Answer Sources panels were removed.
- Add Employee and Edit Employee include a company-scoped optional
  Telephone / Mobile No. field. Existing databases receive the new nullable
  column through the additive runtime schema upgrade.
- The employee list includes and searches the telephone/mobile value.
- The Edit Employee Danger Zone targets the currently selected employee and
  now requires only one acknowledgment checkbox and the permanent-delete
  button.

No destructive database migration is required.


## v8.8.13 Table and Leave Management Hotfix

- Removes the accidental `selected_request_id` reference from Employee Leave Accounts.
- Keeps notification filter reset inside the Leave Requests renderer only.
- Makes the Employee List compact by removing duplicate split-name columns.
- Combines email and telephone/mobile into one Contact column.
- Uses a five-row maximum viewport without a large empty area for shorter lists.
- Keeps Employee Number and Full Name visible while horizontally scrolling.

No destructive database migration is required.


## v8.8.14 Native Copy and Verified Refresh Persistence

- Streamlit runs in viewer toolbar mode, removing developer cache tools
  and leaving Ctrl/Cmd+C as the browser's normal Copy command.
- The old JavaScript copy-key interception is removed.
- Browser-cookie reads refresh the cookie component's internal cache.
- A full refresh gets up to five short restoration cycles before the
  login page is allowed to appear.
- Login and password-change transitions verify that the signed cookie is
  present in the browser before continuing, with a bounded timeout.
- Logout verifies cookie removal before completing.

No database migration is required.


## v8.8.15 Copy and Refresh Root Fix

This release removes two root causes from the previous authentication build:

1. The browser-cookie controller is never refreshed immediately after its
   keyed constructor call. The initial component is mounted once, and Login is
   shown only after its first result is available.
2. Cookie write/remove transitions no longer re-read or refresh the same
   component during the same Streamlit run.

Ctrl/Cmd+C now uses a parent-window capture listener that stops Streamlit's
Clear-cache shortcut listener without calling `preventDefault`, preserving the
browser's native Copy action.

No database migration is required.


## v8.8.16 Browser-Storage Refresh Fix

Authentication persistence no longer depends on the third-party
`streamlit-cookies-controller` component. A bundled offline Streamlit
component stores the signed token in browser `localStorage`.

Refresh flow:

```text
F5 / browser refresh
→ new Streamlit session
→ bundled component reads localStorage
→ application waits for ready response
→ signed token is validated against the database
→ same user, portal, and URL-selected page are restored
```

Login, password change, logout, and external password reset all use the same
storage key. The token remains signed, time-limited, password-fingerprint
bound, company-scoped, and invalidated when the account or company is inactive.

The custom component is included in the ZIP and needs no internet connection.
No database migration is required.


## v8.8.17 Single-Submit Login Fix

All three login credentials now belong to one Streamlit form. The Company
Code field no longer uses an external `on_change` rerun that could consume the
first Sign In click.

After successful credential validation, the authenticated Streamlit session
opens the correct portal immediately. Browser-token persistence is retried
non-blockingly from the protected page instead of stopping on the Login page.

The separate full-browser-refresh persistence issue remains an open tracked
item and is not claimed as resolved by this version.

No database migration is required.

## v8.8.19 — Scrollable Policy Management

- Searchable Sections now stays inside a fixed-height scrollable box.
- Version History tables keep a fixed height with vertical scrolling and a sticky header.
- Move to Bin now targets the currently selected policy and uses a confirmation checkbox instead of typed Policy ID confirmation.
- The backend still validates the selected policy ID before moving the version to the Bin.

## v8.8.20 — Visible Policy Scrollbars

- Detected Headings and policy document previews now show a clearly visible scrollbar track and thumb.
- Searchable Sections uses a keyed fixed-height container with an always-reserved vertical scrollbar.
- Extracted Policy Content and Editable Policy Content show visible scrollbars inside their fixed-height text areas.
- Bounded Version History tables use a visible themed vertical scrollbar while keeping the sticky header.
- No database migration is required.

## v8.8.21 — Separated Policy Workspaces

- The Policies area now has separate **Upload Policy File** and **Manage Existing Policy** sub-tabs.
- Upload preview, detected headings, previous versions, and file processing remain inside the upload workspace.
- The active policy table, selector, editing, new-version upload, content, sections, version history, and Move to Bin actions are grouped inside the management workspace.
- The Bin remains a separate main tab, and all visible-scrollbar behavior from v8.8.20 is preserved.
- No database migration is required.

## v8.8.22 — Policy Library Peer Tabs and Preview

- The Policies page now uses four equal-level tabs in this order: **Policies**, **Upload Policy File**, **Manage Existing Policy**, and **Bin**.
- The **Policies** tab contains the active policy list only; the list stays in a fixed-height table with visible vertical and horizontal scrollbars and a sticky header.
- A selected policy is not previewed automatically. Its approved content appears below the list only after **Preview Selected Policy** is clicked.
- The read-only preview uses the same bounded detected-heading and extracted-section layout as the upload preview, without edit, version, file, history, or Bin actions.
- **Manage Existing Policy** keeps all maintenance actions but no longer repeats the active policy list table.
- No database migration is required.


## v8.8.23 — Admin Event Calendar Reminders

- Announcements can optionally be added to an event/activity calendar using a local date picker and time input.
- Event end date and time are optional and validated to occur after the start.
- Administrators can schedule an advance reminder for 1 hour, 1 day, 3 days, or 7 days before an event.
- Due reminders create one in-app notification for every active clearance-1 administrator and never notify standard employee accounts.
- Reminder delivery is database-backed and idempotent; refreshes do not create duplicate reminder notifications.
- The new **Calendar & Reminders** tab provides a calendar-date view plus fixed-height, scrollable tables for scheduled and upcoming events.
- Notification clicks open the related announcement through the existing refresh-safe announcement deep link.
- Employee announcement cards display the configured event/activity schedule, while reminder status remains admin-only.
- Existing databases receive additive event and reminder columns without deleting announcement records.

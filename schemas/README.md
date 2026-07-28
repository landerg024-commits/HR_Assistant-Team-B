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

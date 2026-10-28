# Student Group Formation and Skill Matching System

A Django-based web application for managing students, skills, projects, and forming student groups with skill matching and gap analysis.

## Project Purpose

This system helps manage:
- Student records and profiles
- Skills catalog and student skill proficiency levels
- Projects and their required skills with proficiency levels
- Group formation with membership management
- Skill matching analysis and gap detection for groups against project requirements

## Implemented Features

- **Student Management**: CRUD operations for student records (student number, name, email, course, section, year level) with search and pagination. Year level is optional and, when provided, is validated to 1-4.
- **Skill Management**: CRUD operations for skills catalog (search and pagination). Deletion is blocked if the skill is assigned to a student or required by a project.
- **Student Skills**: Assign skills to students with proficiency levels (1-5 scale), with validation and prevention of duplicate assignments.
- **Project Management**: CRUD operations for projects (search and pagination). Deletion is blocked if the project has required skills defined.
- **Project Required Skills**: Define skill requirements per project with required proficiency levels (1-5 scale), with validation and prevention of duplicate requirements.
- **Group Formation & Membership**: Create groups per project, add/remove members (max 5 members per group as enforced in views), and prevent a student from joining more than one group on the same project.
- **Skill Gap Analysis**: Per-group analysis showing satisfied/deficient/missing skills, match percentage, and detailed information per required skill (status, best level in group, covering student, and gap).
- **Group Recommendation Engine**: Recommends eligible students for a given group based on the project's required skills and each student's proficiency levels. Recommendations report skill coverage percentages, counts of covered/required skills, and lists of met/satisfied and missing skills. Students already assigned to any group on the same project are excluded from recommendations. The system assists with manual group formation; it does not automatically create groups or assign members.
- **Authentication**: Login-required access to management features (via `@login_required`). Some admin/user management views are restricted to superusers.
- **Search & Pagination**: Filterable lists across entities where implemented.


## Team Members

- John Carl V. Cuayzon
- Ryan M. Balinas
- John Cris G. Egca

## Prerequisites

- Python 3.12+ (tested in this environment)
- MySQL/MariaDB server
- pip (Python package manager)

## Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/cuayzonjohncarl/BSIT3A-DJANGO-Student-Group-Formation-and-Skill-Matching-System.git
cd BSIT3A-DJANGO-Student-Group-Formation-and-Skill-Matching-System
```

### 2. Create and activate virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Dependencies:
- Django==5.0.14
- mysqlclient==2.2.8
- openpyxl==3.1.5

### 4. Database Setup (MySQL/MariaDB)

**Important Notes:**
- The student-domain models (`Student`, `Skill`, `StudentSkill`, `Project`, `ProjectRequiredSkill`, `Group`, `GroupMember` in `apps.students`) are declared as `managed = False`. **Their tables must already exist in the database - do not rely on Django migrations to create or alter them.**
- Do **not** delete, reset, recreate, or overwrite the existing database or its data.
- The `apps.info` app has migrations (see `apps/info/migrations/0001_initial.py`) and uses table `tblinfo`.
- `apps.core` and `apps.users` have models with default managed behavior (Django auth/admin tables are managed by Django; migrations are available for managed apps as configured).

**Steps:**

1. Create a MySQL/MariaDB database named `student_group_matching` (matching the configuration in `mysite/settings.py`):
```sql
CREATE DATABASE student_group_matching CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

2. Ensure the required tables exist. You can use the provided SQL dump:
   - `bsitcrud.sql` - contains database schema/data
   - See `DATABASE_DESIGN.md` for the table structure

3. Update database credentials in `mysite/settings.py` if needed. The default configuration uses:
   - ENGINE: `django.db.backends.mysql`
   - NAME: `student_group_matching`
   - USER: `root`
   - PASSWORD: `` (empty)
   - HOST: `localhost`
   - PORT: `3306`

   **You must supply your own database credentials if they differ. Never commit credentials to version control.**

4. Run migrations for managed apps only:
```bash
python manage.py migrate
```

This will create Django's auth, session, admin, and content type tables, plus any managed app tables (e.g., `tblinfo` from `apps.info`). Because `apps.students` models are `managed = False`, migrations will not create/alter those tables — ensure they pre-exist in the configured database.

### 5. Create a superuser (optional)

```bash
python manage.py createsuperuser
```

### 6. Run the development server

```bash
python manage.py runserver
```

Access the application at `http://127.0.0.1:8000/`

## Testing

The project includes tests in `apps/students/tests.py`, `apps/core/tests.py`, `apps/users/tests.py`, and `apps/info/tests.py`. Tests can be run in two modes:

### Default settings (MySQL/MariaDB)
Uses the database configuration from `mysite/settings.py` (MySQL/MariaDB as configured).

**Verified behavior (in this environment):**
```bash
python manage.py test apps.students.tests
```
- Found 90 tests
- Ran successfully with `OK (skipped=62)` (62 skipped). Many DB-backed CRUD/integration tests are skipped under the default settings depending on environment; a MariaDB Strict Mode warning may be reported.

**When to use:** To test against your configured MySQL/MariaDB instance. Note that the `students` app models are `managed = False` and expect pre-existing tables; some tests are introspective and will run regardless, while others may be skipped depending on the test environment.

### Test settings (SQLite in-memory - recommended for isolated testing)
Uses `mysite/test_settings.py` which overrides the database to an in-memory SQLite database.

**Verified behavior (in this environment):**
```bash
python manage.py test apps.students.tests --settings=mysite.test_settings
```
- Found 90 tests
- All 90 tests passed with zero failures and zero skips (`Ran 90 tests ... OK`)
- Uses `UnmanagedTablesMixin` which creates the unmanaged tables (Student, Skill, StudentSkill, Project, ProjectRequiredSkill, Group, GroupMember) only in the throwaway test database via Django's schema editor

**When to use:** For isolated, reliable testing without touching your MySQL/MariaDB database. This exercises DB-backed CRUD flows, group/matching logic, and group recommendation functionality.

**Important:** Running with `mysite.test_settings` (SQLite in-memory) does **not** prove that every operation works against the actual MySQL/MariaDB database. Differences in SQL dialects, constraints, collation, data types, and the fact that models are `managed = False` (requiring pre-existing tables) mean MySQL/MariaDB behavior should be verified separately in an environment with a properly configured instance containing the required schema. The SQLite test run is for isolated verification of application logic only.


## Project Structure

```
apps/
├── core/       # Core functionality (dashboard)
├── info/       # Info app (managed, has migrations)
├── students/   # Main app - student/group/skill management (unmanaged models)
├── users/      # User management/authentication
mysite/         # Project settings and URL configuration
templates/      # HTML templates (Tabler UI framework)
static/         # Static files (CSS, JS)
```

## Additional Documentation

- `DATABASE_DESIGN.md` - Detailed database schema design
- `bsitcrud.sql` - Database dump/schema
- `documentation/BSIT-Concept-Paper-Student-Group-Formation.pdf` - Project concept paper

## Limitations / Planned Work

Based on inspection of the codebase (as implemented), the following from the original concept paper are not fully implemented or not verified in the current codebase:

- **Automatic group formation**: Not implemented. The system provides group management and a recommendation endpoint to assist with manual formation; it does not auto-generate groups or auto-assign members.
- **Separate Administrator/Instructor/Student permissions/roles**: Not implemented as distinct role-based access control for these groups. Access control is primarily login-required (`@login_required`); some user management views are restricted to superusers (`@user_passes_test(_is_superuser, ...)`). There is no evidence of separate Administrator/Instructor/Student role groups/permissions enforced across all features.
- **Analytics dashboard**: Not implemented as a dedicated analytics feature. The home/dashboard (`apps.core.views.home`, route `home/` named `dashboard`) shows basic counts (students, skills, projects, groups) and group match percentages using `_analyze_group_skills`, but there is no comprehensive analytics/reporting dashboard as described in the concept paper.

Other notes:
- All management URLs require authentication (`@login_required`). Login is available via auth routes.
- The system enforces business rules like preventing duplicate assignments, max group size (5 members), and students belonging to only one group per project.
- Skill matching/gap analysis uses actual database records to compute coverage based on student proficiency vs project requirements.
- Year levels are validated as integers 1-4 (1st through 4th Year) when provided; proficiency and required levels are validated as integers 1-5 in the relevant forms/validations.

# Student Group Formation and Skill Matching System

A web-based academic project developed by BSIT students to support student skill management, project requirement tracking, and more balanced group formation.

## Project Information

- **Project Title:** Development of a Web-Based Student Group Formation and Skill Matching System
- **Course:** Bachelor of Science in Information Technology (BSIT 3A)
- **Developers:**
  - John Carl V. Cuayzon
  - Ryan M. Balinas
  - John Cris G. Egca
- **Backend:** Python and Django
- **Database:** MySQL / MariaDB
- **Frontend:** HTML, CSS, JavaScript, and Bootstrap

## About the Project

Traditional student group formation often relies on random assignments, student self-selection, or other methods that may not consider individual technical skills. These approaches can result in unbalanced teams, missing competencies, and difficulties completing academic projects.

The Student Group Formation and Skill Matching System aims to address these challenges through a centralized web-based platform that manages student profiles, technical skills, project requirements, and group information.

The system is intended to help instructors make more informed group formation decisions by considering students' skills and the competencies required for a project.

## Project Objectives

The main objective is to develop a web-based system that supports skill-based student group formation for academic projects.

Specifically, the project aims to:

1. Manage student profiles and technical skill information.
2. Maintain a catalog of technical skills and proficiency levels.
3. Record projects and their required technical competencies.
4. Evaluate group skill coverage and identify potential skill gaps.
5. Recommend suitable students based on group skill requirements.
6. Support secure access and administrative management.

## Key Features

Every feature listed below is implemented in the current codebase and covered by the automated test suite (`python manage.py test --settings=mysite.test_settings`).

### Authentication and Session Security
- Registration with server-side validation and Django's password validators.
- Login with failure counting and a one-minute lockout after 5 failed attempts (session based).
- Login/logout redirects and CSRF protection on every mutating form and AJAX endpoint.

### Role-Based Authorization (Administrator, Instructor, Student)
- Roles are stored in Django's built-in `auth_group` / `auth_user_groups` tables, so enabling roles requires **no schema change**.
- Administrators manage user accounts and assign roles; Instructors manage academic records; Students have read-only access to academic data.
- Permissions are enforced inside the views: AJAX mutations return HTTP 403 with a JSON error, page requests are redirected with an explanatory message. Hiding buttons is only a convenience layer on top of that enforcement.
- Accounts created through registration are assigned the **Student** role; accounts created before roles existed keep their previous access (**Instructor**).

### Student Management
- Searchable, paginated student directory with modal-driven AJAX create/edit/delete.
- Student number, name, email, course, section and year level (1-4) with input validation and duplicate student-number prevention.

### Skills Management
- CRUD for the technical skill catalog with duplicate-name prevention (case-insensitive).
- Student-skill assignments on the five-point proficiency scale: **1 Beginner, 2 Elementary, 3 Intermediate, 4 Advanced, 5 Expert**, with duplicate-assignment prevention.

### Project Management
- CRUD for academic projects and their required skills.
- Each requirement stores a minimum proficiency level validated against the 1-5 scale.
- Deletion is blocked while a project still has requirements or groups.

### Skill Matching Engine
- Computes a 0-100 compatibility index between each student's skill inventory and a project's requirement matrix.
- Every score is reproducible from the stored levels and is shown with a plain-language explanation plus a per-requirement breakdown (met / short by N / missing).
- Whole-cohort view: requirement matrix with per-skill coverage, average index, fully matched and missing-skill counters.

### Automated Balanced Group Formation
- Distributes the unassigned students of a project into balanced teams, seeded by strength and filled by marginal requirement coverage.
- Respects the group size limit (2-5 members), prevents duplicate assignments across a project, and reports students that do not fit.
- Handles students with no recorded skills, missing requirements, and empty pools with explicit warnings instead of silent failures.
- Preview-first workflow: the plan is computed and rendered without writing anything; groups are only created when an instructor confirms, in a single transaction.

### Skill Gap Analysis
- Per group: satisfied / deficient / missing requirements, the best member level for each requirement, the covering student, and two measures - requirement coverage (`match_percentage`) and proficiency-weighted coverage (`weighted_pct`).

### Member Recommendations
- Ranks students that are not yet assigned to the project by the share of the group's outstanding weighted gap they would fill, and explains each suggestion ("Brings Advanced Frontend - covers the required level 3").
- Respects group capacity and excludes students already assigned to any group of that project.

### Analytics Dashboard
- Real database aggregates only: totals for students, skills, projects and groups, requirement satisfaction, and compatibility statistics.
- ApexCharts visualisations: proficiency distribution, requirement status donut, students per course, and per-group compatibility (chart animations respect `prefers-reduced-motion`).

### Administration
- Django admin plus a role-protected user management page (list, search, pagination, create/edit/delete with role assignment).

## Matching Algorithm

For a project with requirements `r_i = (skill, required level L_i)` and a student with proficiency `p_i` (`0` when never recorded):

1. **Achievement** per requirement: `a_i = min(p_i / L_i, 1)` - over-qualification is capped, so a level-5 student cannot score above 100% for a level-3 requirement.
2. **Weighted coverage**: `C = sum(L_i * a_i) / sum(L_i)` - harder requirements weigh more.
3. **Compatibility index**: `round(100 * C)`.
4. **Status per requirement**: `met` (`p_i >= L_i`), `deficient` (`0 < p_i < L_i`), `missing` (`p_i = 0`).

Group gap analysis uses the same inputs: the best proficiency among the members is compared with each requirement, producing `satisfied` / `deficient` / `missing` plus the number of levels short (`gap`).

## Automated Group Formation Algorithm

Implemented in `apps/students/group_formation.py` and deterministic for a given input:

1. **Eligibility** - only students not already assigned to a group of this project are considered.
2. **Ranking** - students are ordered by requirements met, then weighted capped proficiency, then surname, forename and id.
3. **Group count** - `ceil(students / max_members)` unless the instructor requests a specific number (validated and clamped).
4. **Seeding** - the strongest `k` students start the `k` groups, one each.
5. **Greedy fill** - each remaining student joins the group where they add the most weighted coverage; ties go to the smaller group, then the lower group index. Students that do not fit are reported as unassigned.
6. **Rebalancing** - a bounded pass of single moves and swaps is accepted only when it improves `(minimum group coverage, -spread)`.
7. **Reporting** - per-group coverage, unmet requirements, unassigned students and warnings (empty pool, missing requirements, students without recorded skills, capacity overflow).

Saving recomputes the plan server-side (client data is never trusted), creates the groups and memberships inside one transaction, and de-duplicates memberships.

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3.12 |
| Web Framework | Django 5.0 |
| Database | MySQL / MariaDB |
| Frontend | HTML5, CSS3, JavaScript, AJAX (Fetch) |
| UI Framework | Bootstrap 5 + Tabler UI dashboard theme |
| Charts | ApexCharts (vendored in `static/libs`) |
| Icons | Font Awesome 6 |
| Database Testing | In-memory SQLite (`mysite.test_settings`) |
| Testing Framework | Django Test Framework |

## Database

The project uses a relational database named `student_group_matching`.

The database includes tables for:

- Students
- Skills
- Student skills
- Projects
- Project required skills
- Groups
- Group members
- Django authentication tables (`auth_user`, `auth_group`, `auth_user_groups`) - the three role groups are stored in `auth_group`

The database configuration and existing schema must be preserved when running the application. The academic models are declared with `managed = False`, so Django never creates, alters or drops those tables and no migration is applied to them. **No schema change was required for any feature described in this README.**

## Installation and Setup

### Prerequisites

Install or prepare the following:

- Python 3.12
- MySQL or MariaDB
- Git
- Visual Studio Code (optional)

### 1. Clone the Repository

```bash
git clone https://github.com/cuayzonjohncarl/BSIT3A-DJANGO-Student-Group-Formation-and-Skill-Matching-System.git
```

### 2. Open the Project Folder

```bash
cd BSIT3A-DJANGO-Student-Group-Formation-and-Skill-Matching-System
```

### 3. Activate the Virtual Environment

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If the virtual environment does not exist, create it first using an installed compatible Python version:

```powershell
py -3.12 -m venv .venv
```

Then activate it using the command above.

### 4. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 5. Configure the Database

Ensure that MySQL or MariaDB is running and that the `student_group_matching` database exists.

Review `mysite/settings.py` and configure the database connection using your local database credentials. Do not commit database passwords or other secrets to GitHub.

The settings read these optional environment variables and fall back to the local development values when they are unset:

| Variable | Purpose | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key | development fallback in `settings.py` |
| `DJANGO_DEBUG` | `0` turns debug mode off | `1` (debug on) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts (required when debug is off) | empty |
| `DJANGO_DB_NAME` | Database name | `student_group_matching` |
| `DJANGO_DB_USER` | Database user | `root` |
| `DJANGO_DB_PASSWORD` | Database password | empty |
| `DJANGO_DB_HOST` | Database host | `localhost` |
| `DJANGO_DB_PORT` | Database port | `3306` |

**Important:** Check the existing database schema and Django migration configuration before running migrations. Do not run migrations against the existing database without confirming that the changes are safe.

### 6. Run the Django System Check

```powershell
python manage.py check
```

### 7. Start the Development Server

```powershell
python manage.py runserver
```

Open the following address in your browser:

http://127.0.0.1:8000/

The application may require additional database or authentication setup before every page can be used successfully.

## Testing

Run the full suite with the dedicated test settings (this is the only supported way to run tests - it keeps them away from MariaDB):

```powershell
python manage.py test --settings=mysite.test_settings
```

What the suite covers:

- model/table/foreign-key mappings for the unmanaged tables,
- URL resolution and login requirements for every endpoint,
- CRUD and validation for students, skills, assignments, projects, requirements and groups,
- the matching engine (weighted score, capping, statuses, explanations, determinism),
- the gap analysis (satisfied / deficient / missing, weighted coverage),
- member recommendations (exclusion of assigned students, gap-filling rank, explanations),
- automated group formation (group count, capacity, overflow reporting, determinism, complementary skill spread, persistence, duplicate-name handling),
- formation endpoint permissions (anonymous redirect, student 403, instructor success),
- role resolution and role assignment, user-management authorization, registration role assignment,
- dashboard aggregates and every chart series.

The test database is an in-memory SQLite instance created and destroyed by the runner; the unmanaged tables are created explicitly by `UnmanagedTablesMixin` inside that throwaway database only.

## User Roles

| Role | Capabilities |
|---|---|
| Administrator | Everything below, plus user account management and role assignment |
| Instructor | Students, skills, student skills, projects, requirements, groups, formation preview/save, matching engine |
| Student | Read-only access to academic pages; manages only their own Info records |

Promote or demote accounts on the **Users** page (Administrator only).

## Scope and Limitations

The system focuses on structured technical skills and project requirements. It does not evaluate personality, psychological traits, or student schedule compatibility.

Student proficiency assessments rely on self-reported information and instructor verification; there is no automated code assessment or third-party credential check.

Known limitations of the current implementation:

- **Student self-service is read-only.** Student accounts are not linked to rows in the `students` table (there is no `users` column on that table and adding one would be a schema change), so a student cannot yet edit their own proficiency records. Instructors manage those records.
- **Rate limiting is session based.** The login lockout counts failures per browser session, not per IP or account, so it protects casual brute force but not a distributed attack.
- **No external integrations.** Email delivery, SMS alerts and LMS (Canvas/Moodle) synchronization are out of scope, as stated in the concept paper.
- **Single-server deployment assumed.** The design targets an institutional intranet or lab server; there is no container/CI deployment configuration in the repository.

## Future Improvements

- Link user accounts to student records so students can self-report proficiencies (requires a schema change and therefore explicit approval).
- Account-wide and IP-based rate limiting with CAPTCHA or 2FA for administrators.
- Export of group plans and compatibility reports (CSV/PDF).
- Course/section aware formation constraints and project-specific group sizes.
- Deployment hardening: `DJANGO_SECRET_KEY`, HTTPS, and a production WSGI server.

## Project Status

**Status:** Core functional requirements implemented and verified (137 automated tests passing), UI/UX refinement in progress.

Implemented and verified against the concept paper's final-phase objectives: algorithmic skill matching, automated group formation with skill gap identification, intelligent member recommendations, role-based authorization, and the analytics dashboard. Further usability evaluation and documentation continue as part of the BSIT academic requirements.

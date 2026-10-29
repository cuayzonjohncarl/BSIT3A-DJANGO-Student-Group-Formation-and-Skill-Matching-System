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

The following features are part of the project's current implementation and development scope. Individual features should be verified against the latest working version.

### Student Management
- Maintain student records and academic information.
- View and manage student profiles.
- Support student directory operations.

### Skills Management
- Maintain a catalog of technical skills.
- Associate students with their technical skills.
- Represent proficiency using a five-point scale.

### Project Management
- Manage academic project information.
- Define required skills for individual projects.
- Specify minimum proficiency levels for required skills.

### Group Management and Skill Matching
- Manage project groups and group membership.
- Review group composition in relation to project requirements.
- Identify skill coverage and potential competency gaps.
- Recommend potential group members based on skill requirements.

### Authentication and Administration
- Provide account registration and login functionality.
- Use Django's authentication and administration facilities where configured.
- Support administrative management of project data.

**Development note:** Automated group formation, fully implemented role-specific permissions, and a complete analytics dashboard must be verified before being described as finished features.

## Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python 3 |
| Web Framework | Django 5 |
| Database | MySQL / MariaDB |
| Frontend | HTML5, CSS3, JavaScript |
| UI Framework | Bootstrap 5 |
| Database Testing | SQLite test configuration |
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

The database configuration and existing schema must be preserved when running the application. Some project models may use existing database tables rather than Django-managed migrations.

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

To run the project's automated tests with the dedicated test settings, use:

```powershell
python manage.py test --settings=mysite.test_settings
```

Review the test output to determine whether the tests pass, fail, or are skipped in your current environment.

## Scope and Limitations

The system focuses on structured technical skills and project requirements. It does not currently claim to evaluate personality, psychological traits, or student schedule compatibility.

Student proficiency assessments may rely on self-reported information and instructor verification.

The completeness of automated group formation, role-specific access permissions, and analytics features depends on the current implementation and requires verification.

## Future Improvements

Potential improvements include:

- Automated formation of balanced student groups.
- More comprehensive skill matching and compatibility scoring.
- Improved skill gap analysis.
- Enhanced group member recommendations.
- Separate permissions for administrators, instructors, and students.
- A comprehensive analytics dashboard.
- Additional usability and reliability testing.

## Project Status

**Status:** Under Development

This project is being developed incrementally as part of the BSIT academic requirements. Features and documentation may change as development, testing, and evaluation continue.

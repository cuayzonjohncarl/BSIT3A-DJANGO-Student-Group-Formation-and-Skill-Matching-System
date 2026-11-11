# INITIAL DATABASE TABLE DESIGN

## 1. STUDENTS

| Field | Description | Key |
|---|---|---|
| student_id | Student ID | Primary Key |
| student_number | Student Number | |
| first_name | First Name | |
| last_name | Last Name | |
| email | Email Address | |
| course | Course | |
| section | Section | |
| year_level | Year Level (1 = 1st, 2 = 2nd, 3 = 3rd, 4 = 4th; optional) | |

## 2. SKILLS

| Field | Description | Key |
|---|---|---|
| skill_id | Skill ID | Primary Key |
| skill_name | Name of Skill | |
| description | Skill Description | |

## 3. STUDENT_SKILLS

| Field | Description | Key |
|---|---|---|
| student_skill_id | Student Skill ID | Primary Key |
| student_id | Student ID | Foreign Key |
| skill_id | Skill ID | Foreign Key |
| proficiency_level | Student Skill Level | |

## 4. PROJECTS

| Field | Description | Key |
|---|---|---|
| project_id | Project ID | Primary Key |
| project_name | Project Name | |
| description | Project Description | |
| created_at | Date Created | |

## 5. PROJECT_REQUIRED_SKILLS

| Field | Description | Key |
|---|---|---|
| project_skill_id | Project Skill ID | Primary Key |
| project_id | Project ID | Foreign Key |
| skill_id | Skill ID | Foreign Key |
| required_level | Required Skill Level | |

## 6. GROUPS

| Field | Description | Key |
|---|---|---|
| group_id | Group ID | Primary Key |
| project_id | Project ID | Foreign Key |
| group_name | Group Name | |
| created_at | Date Created | |

## 7. GROUP_MEMBERS

| Field | Description | Key |
|---|---|---|
| group_member_id | Group Member ID | Primary Key |
| group_id | Group ID | Foreign Key |
| student_id | Student ID | Foreign Key |

## 8. DJANGO AUTHENTICATION TABLES (role storage)

The three application roles are stored in Django's built-in tables, so **no new table or column was added** for role-based authorization.

| Table | Purpose |
|---|---|
| auth_user | Account records (username, name, email, password hash, flags) |
| auth_group | Role containers: `Administrator`, `Instructor`, `Student` |
| auth_user_groups | Links an account to its role group |
| auth_group_permissions / auth_user_user_permissions | Standard Django permissions (unused by the custom role checks) |

Role resolution order: superuser -> `Administrator` -> `Instructor` -> `Student` -> default (`Instructor`, for accounts created before roles existed).

## DATABASE RELATIONSHIPS

- One student can have many skills.
- One skill can belong to many students.
- One project can require many skills.
- One skill can be required by many projects.
- One project can have many groups.
- One group can have many students.
- One student can belong to a group.
- One user can belong to one role group; a user's own `Info` records are scoped by `tblinfo.user_id`.
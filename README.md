# Development of a Web-Based Student Group Formation and Skill Matching System

*BSIT Class Project Concept Paper*

## 1. Project Title and Proponents

- **Project title:** Development of a Web-Based Student Group Formation and Skill Matching System
- **Proponents:** John Carl V. Cuayzon, Ryan M. Balinas, John Cris G. Egca
- **Program:** Bachelor of Science in Information Technology (BSIT 3A)

## 2. Introduction

### Background of the Project

Collaborative learning and group-based capstone projects are fundamental components of the Bachelor of Science in Information Technology (BSIT) curriculum. In many academic settings, instructors form project teams through randomized grouping, student self-selection, or fixed roster segmentation. These methods can produce unbalanced teams: proficient programmers may be concentrated in one group, while other groups lack essential competencies such as database design, interface development, or systems analysis. Students who are less socially connected may also be isolated by self-selection. When competency gaps become apparent during the semester, teams often face uneven workloads, delayed milestones, interpersonal conflict, and lower deliverable quality.

To address these problems, the proponents developed a centralized, web-based Student Group Formation and Skill Matching System using Python and the Django framework. The current implementation digitizes student profiles, technical skills, five-point proficiency records, academic projects, and project requirement matrices. It computes compatibility indices, analyzes group-level skill gaps, recommends unassigned students, and generates balanced project groups. The system also provides role-based access for administrators, instructors, and students; session security; and an analytics dashboard. Remaining work focuses on user acceptance testing and deployment hardening rather than on additional core modules.

### Statement of the Problem or Project Objectives

The main objective of the project is to design, develop, and evaluate a web-based Student Group Formation and Skill Matching System that automates technical profiling, matches complementary skills against project requirements, and supports balanced collaborative team formation.

Specifically, the project aims to accomplish the following technical objectives:

1. Maintain a secure student and skills repository that records student profiles, technical skills, and proficiency ratings on a five-point scale.
2. Maintain a project requirement module that maps each academic project to required skills and minimum proficiency levels.
3. Implement an algorithmic skill matching engine that computes a 0–100 compatibility index for each student and explains each requirement result.
4. Implement automated group formation and skill-gap identification that organizes eligible students into balanced teams and compares group rosters with project requirements.
5. Implement a member recommendation feature that ranks unassigned students by how much of a group's remaining skill gap they would fill.
6. Enforce role-based authorization for Administrator, Instructor, and Student accounts and maintain session security and automated tests.
7. Conduct user acceptance testing with instructors and students to evaluate usability, reliability, and operational fit. This activity is planned and has not yet been completed.

### Significance of the Project

**Course instructors and capstone advisers:** The system reduces manual grouping work, makes the selection process transparent, and shows requirement coverage and skill gaps before project deadlines. It supports, rather than replaces, instructor judgment.

**BSIT students:** The system places students in teams using recorded competencies and makes individual strengths and growth areas visible. Student accounts currently have read-only access to academic data.

**Academic departments and administrators:** The system produces aggregated counts of student skills, project requirements, group coverage, and gap status. These data can support curriculum review and instructional planning, but the system does not yet produce formal institutional reports.

**Future researchers and student developers:** The implementation provides a modular Django reference for role-based academic applications, unmanaged legacy schemas, explainable matching, and deterministic group formation.

### Alignment with Institutional Research Agenda and Sustainable Development Goals

**Institutional Research Agenda Alignment:** The project is intended to contribute to the institution's research on information technology applications in education and academic administration. It demonstrates a working decision-support platform for skills management and team formation. The specific institutional research priority for the current academic year was not available for verification while this paper was prepared, so no specific priority title is claimed; the alignment should be confirmed by the program adviser.

**Sustainable Development Goal Alignment:**

- **SDG 4 (Quality Education, Target 4.4):** The system supports the development of relevant technical and collaborative skills by helping instructors compose teams with complementary competencies and by giving students a structured view of their proficiency profile.
- **SDG 9 (Industry, Innovation, and Infrastructure):** The system introduces a digital academic platform designed to replace ad hoc or paper-based grouping practices and provides a reusable foundation for skills-based academic decision support.
- **SDG 10 (Reduced Inequalities):** The system bases group composition on recorded proficiencies rather than social affinity. This design is intended to reduce social bias in team formation and to give less socially connected students a fairer opportunity to be placed in balanced teams.

## 3. Scope and Limitations

### System Scope & Technical Architecture

The system is a web-based academic platform for departments that conduct group-based computing projects. It is implemented as a Django Model-View-Template application with separate modules for authentication, user administration, personal information, and academic functions. The subsections below summarize the implemented, partially implemented, and planned components.

### Implemented Components

| Component | Description and coverage |
|---|---|
| **Core academic modules** | Authentication and session security; role-based authorization for Administrator, Instructor, and Student; student, skill, five-point proficiency, project, and project-requirement records. |
| **Matching, analysis, and formation** | 0–100 compatibility index with per-requirement explanations; skill-gap analysis for satisfied, deficient, and missing requirements; member recommendations; automated balanced formation with preview, configurable size (2–5), and transactional saving. |
| **Administration and support** | Analytics dashboard with aggregates and ApexCharts; user and role administration; user-scoped personal information; Django administration; demo-data command; automated tests for models, routes, validation, matching, formation, and dashboard. |

### Partially Implemented Components

- **Student self-service:** Read-only because accounts are not linked to student records; instructors manage proficiency data.
- **Login lockout:** Session-only, with no account-wide or IP throttling.
- **Academic tables:** The seven academic tables are unmanaged and require manual provisioning.

### Planned Future Components

The following components are planned for a future phase:

- User acceptance testing
- Account-to-student linking
- CSV/XLSX/PDF export
- Course, section, and schedule constraints
- Production hardening
- Optional email, SMS, or LMS integrations

### Technology Stack

- **Backend:** Python 3.12.10, Django 5.0.14, MariaDB 10.4.32 (MySQL-compatible), mysqlclient 2.2.8
- **Frontend:** HTML5, CSS3, JavaScript with Fetch/AJAX, Bootstrap 5, Tabler UI, ApexCharts, Font Awesome 6
- **Testing:** Django Test Framework with in-memory SQLite

### Target Users

Course instructors and capstone advisers, BSIT students, and system administrators.

### Data and Deployment

MariaDB database `student_group_matching` with seven unmanaged academic tables (`students`, `skills`, `student_skills`, `projects`, `project_required_skills`, `groups`, and `group_members`), Django authentication tables, and `tblinfo`. Current development deployment: Windows, XAMPP, single Django development server.

### Limitations

- **Scope of matching logic:** The matching engine evaluates structured technical proficiency levels (1–5) and project requirement levels (1–5). It does not assess personality, psychometric attributes, or schedule availability.
- **Assessment of student skills:** Proficiency ratings are recorded manually and depend on instructor input. The system does not provide a student self-assessment workflow, perform automated coding assessments, execute code, or verify third-party credentials.
- **Student account integration:** Student accounts are not linked to rows in the `students` table. Students can view academic information but cannot create or edit their own proficiency records; instructors manage those records.
- **Database management:** The seven academic tables are unmanaged. They must be provisioned and backed up outside Django migrations, and direct database or Django admin edits can bypass application validation.
- **Authentication security:** Login lockout is session-based and does not provide account-wide or IP-based throttling, CAPTCHA, or multi-factor authentication.
- **Reporting and external integration:** The system does not yet export group plans or reports to CSV, XLSX, or PDF and does not integrate with email, SMS, or learning management systems.
- **Deployment environment:** The current deployment target is a single development server. Containerization, continuous integration, production web-server configuration, and formal backup procedures are not included.
- **Evaluation:** Formal user acceptance testing has not yet been conducted. This paper describes the system design and implementation status; it does not report evaluation results.

"""Seed repeatable demonstration data for the group formation and matching system.

The command only creates the records listed in this module. It never updates or
deletes records that were not created by this command unless ``--clear`` is
explicitly requested. Sample students, projects, groups and skills use exact
identifiers so running the command again reuses the existing sample rows
instead of creating duplicates.
"""

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.students.models import (
    Group,
    GroupMember,
    Project,
    ProjectRequiredSkill,
    Skill,
    Student,
    StudentSkill,
)


BASELINE_SKILLS = [
    'Backend Web Development',
    'Frontend Web Development',
    'Database Design & Management',
    'UI/UX Design & Prototyping',
    'Systems Analysis & Documentation',
    'Quality Assurance & Software Testing',
    'Mobile Application Development',
]

NEW_SKILLS = {
    'Python Programming': (
        'Writing readable Python scripts, modules, and backend logic for '
        'academic and web applications.'
    ),
    'JavaScript & TypeScript': (
        'Building interactive browser behavior and typed front-end logic with '
        'modern JavaScript and TypeScript.'
    ),
    'REST API Development': (
        'Designing and implementing RESTful endpoints, request validation, and '
        'JSON integrations between clients and servers.'
    ),
    'Cloud Deployment & DevOps': (
        'Deploying web applications to cloud platforms and automating builds, '
        'releases, and environment configuration.'
    ),
    'Cybersecurity Fundamentals': (
        'Applying authentication, authorization, secure coding, and basic '
        'vulnerability prevention practices.'
    ),
    'Data Analysis & Visualization': (
        'Cleaning datasets and presenting insights through charts, summaries, '
        'and analytical dashboards.'
    ),
    'Machine Learning Fundamentals': (
        'Preparing data and training basic predictive models using standard '
        'machine learning workflows.'
    ),
    'Agile Project Management': (
        'Planning sprints, managing backlogs, and coordinating team '
        'deliverables using Agile practices.'
    ),
    'Technical Writing': (
        'Producing clear documentation, user guides, reports, and software '
        'specifications.'
    ),
    'Networking Fundamentals': (
        'Understanding IP addressing, network devices, protocols, and basic '
        'connectivity troubleshooting.'
    ),
    'IoT & Embedded Systems': (
        'Integrating sensors, microcontrollers, and network modules into small '
        'connected-device prototypes.'
    ),
    'React Development': (
        'Building component-based user interfaces and managing state in React '
        'applications.'
    ),
    'Graphic Design & Branding': (
        'Creating visual assets, layout systems, and consistent branding for '
        'digital products.'
    ),
}

PROJECTS = [
    {
        'name': 'Campus Event Management Portal',
        'description': (
            'A web portal for creating campus events, handling student '
            'registration, tracking attendance, and generating event reports.'
        ),
        'requirements': [
            ('Frontend Web Development', 4),
            ('Backend Web Development', 4),
            ('Database Design & Management', 3),
            ('UI/UX Design & Prototyping', 3),
            ('Quality Assurance & Software Testing', 2),
        ],
    },
    {
        'name': 'Student Attendance Mobile App',
        'description': (
            'A cross-platform mobile application for QR-based attendance, '
            'offline check-in, and instructor attendance reports.'
        ),
        'requirements': [
            ('Mobile Application Development', 4),
            ('Backend Web Development', 3),
            ('REST API Development', 3),
            ('Database Design & Management', 3),
            ('UI/UX Design & Prototyping', 3),
        ],
    },
    {
        'name': 'Learning Analytics Dashboard',
        'description': (
            'An instructor dashboard that visualizes student performance, '
            'attendance, and skill proficiency trends.'
        ),
        'requirements': [
            ('Data Analysis & Visualization', 4),
            ('Database Design & Management', 4),
            ('Frontend Web Development', 3),
            ('Python Programming', 3),
            ('Agile Project Management', 3),
        ],
    },
    {
        'name': 'Smart Campus IoT Monitoring System',
        'description': (
            'An IoT system that monitors laboratory temperature, humidity, and '
            'equipment usage and sends alerts.'
        ),
        'requirements': [
            ('IoT & Embedded Systems', 4),
            ('Networking Fundamentals', 3),
            ('Backend Web Development', 3),
            ('Cybersecurity Fundamentals', 3),
            ('Database Design & Management', 2),
        ],
    },
]

STUDENTS = [
    {
        'student_number': '2026-1101',
        'first_name': 'Alyssa Marie',
        'last_name': 'Bautista',
        'email': 'alyssa.bautista@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Frontend Web Development', 4),
            ('React Development', 4),
            ('UI/UX Design & Prototyping', 3),
            ('JavaScript & TypeScript', 3),
        ],
    },
    {
        'student_number': '2026-1102',
        'first_name': 'Joshua Emmanuel',
        'last_name': 'Dela Cruz',
        'email': 'joshua.delacruz@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Backend Web Development', 4),
            ('Python Programming', 4),
            ('Database Design & Management', 3),
            ('REST API Development', 3),
        ],
    },
    {
        'student_number': '2026-1103',
        'first_name': 'Angela Faith',
        'last_name': 'Reyes',
        'email': 'angela.reyes@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Database Design & Management', 3),
            ('Backend Web Development', 3),
            ('Quality Assurance & Software Testing', 3),
            ('Systems Analysis & Documentation', 2),
        ],
    },
    {
        'student_number': '2026-1104',
        'first_name': 'Mark Angelo',
        'last_name': 'Mendoza',
        'email': 'mark.mendoza@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('UI/UX Design & Prototyping', 4),
            ('Graphic Design & Branding', 4),
            ('Frontend Web Development', 2),
            ('Technical Writing', 2),
        ],
    },
    {
        'student_number': '2026-1105',
        'first_name': 'Patricia Anne',
        'last_name': 'Garcia',
        'email': 'patricia.garcia@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Quality Assurance & Software Testing', 4),
            ('Technical Writing', 3),
            ('Systems Analysis & Documentation', 2),
            ('Agile Project Management', 2),
        ],
    },
    {
        'student_number': '2026-1106',
        'first_name': 'Christian Paul',
        'last_name': 'Navarro',
        'email': 'christian.navarro@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Mobile Application Development', 4),
            ('UI/UX Design & Prototyping', 3),
            ('JavaScript & TypeScript', 3),
            ('React Development', 2),
        ],
    },
    {
        'student_number': '2026-1107',
        'first_name': 'Nicole Anne',
        'last_name': 'Torres',
        'email': 'nicole.torres@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Backend Web Development', 3),
            ('Database Design & Management', 3),
            ('Python Programming', 3),
            ('Cloud Deployment & DevOps', 2),
        ],
    },
    {
        'student_number': '2026-1108',
        'first_name': 'Daniel James',
        'last_name': 'Flores',
        'email': 'daniel.flores@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Database Design & Management', 3),
            ('Quality Assurance & Software Testing', 3),
            ('Backend Web Development', 2),
            ('Technical Writing', 2),
        ],
    },
    {
        'student_number': '2026-1109',
        'first_name': 'Samantha Joy',
        'last_name': 'Ramos',
        'email': 'samantha.ramos@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('UI/UX Design & Prototyping', 3),
            ('Mobile Application Development', 3),
            ('Technical Writing', 2),
            ('Systems Analysis & Documentation', 2),
        ],
    },
    {
        'student_number': '2026-1110',
        'first_name': 'Kevin Louis',
        'last_name': 'Santos',
        'email': 'kevin.santos@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Quality Assurance & Software Testing', 3),
            ('Networking Fundamentals', 2),
            ('JavaScript & TypeScript', 2),
            ('Mobile Application Development', 2),
        ],
    },
    {
        'student_number': '2026-1111',
        'first_name': 'Mary Grace',
        'last_name': 'Villanueva',
        'email': 'marygrace.villanueva@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Data Analysis & Visualization', 4),
            ('Python Programming', 4),
            ('Database Design & Management', 3),
            ('Machine Learning Fundamentals', 3),
        ],
    },
    {
        'student_number': '2026-1112',
        'first_name': 'John Patrick',
        'last_name': 'Castillo',
        'email': 'johnpatrick.castillo@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Database Design & Management', 3),
            ('Backend Web Development', 3),
            ('Python Programming', 3),
            ('Cloud Deployment & DevOps', 2),
        ],
    },
    {
        'student_number': '2026-1113',
        'first_name': 'Jasmine Rose',
        'last_name': 'Domingo',
        'email': 'jasmine.domingo@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Frontend Web Development', 3),
            ('React Development', 3),
            ('UI/UX Design & Prototyping', 3),
            ('JavaScript & TypeScript', 3),
        ],
    },
    {
        'student_number': '2026-1114',
        'first_name': 'Carlo Miguel',
        'last_name': 'Lim',
        'email': 'carlo.lim@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Agile Project Management', 4),
            ('Systems Analysis & Documentation', 3),
            ('Technical Writing', 3),
            ('Backend Web Development', 2),
        ],
    },
    {
        'student_number': '2026-1115',
        'first_name': 'Andrea Nicole',
        'last_name': 'Cruz',
        'email': 'andrea.cruz@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Data Analysis & Visualization', 3),
            ('Frontend Web Development', 3),
            ('Quality Assurance & Software Testing', 2),
            ('Graphic Design & Branding', 2),
        ],
    },
    {
        'student_number': '2026-1116',
        'first_name': 'Rafael Luis',
        'last_name': 'Dizon',
        'email': 'rafael.dizon@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('IoT & Embedded Systems', 4),
            ('Networking Fundamentals', 3),
            ('Python Programming', 3),
            ('Cloud Deployment & DevOps', 2),
        ],
    },
    {
        'student_number': '2026-1117',
        'first_name': 'Bianca Mae',
        'last_name': 'Salazar',
        'email': 'bianca.salazar@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Networking Fundamentals', 3),
            ('Cybersecurity Fundamentals', 2),
            ('Backend Web Development', 2),
            ('Quality Assurance & Software Testing', 2),
        ],
    },
    {
        'student_number': '2026-1118',
        'first_name': 'Gabriel Angelo',
        'last_name': 'Mercado',
        'email': 'gabriel.mercado@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Backend Web Development', 3),
            ('REST API Development', 2),
            ('Python Programming', 2),
            ('Cloud Deployment & DevOps', 2),
        ],
    },
    {
        'student_number': '2026-1119',
        'first_name': 'Erika Jane',
        'last_name': 'Pascual',
        'email': 'erika.pascual@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('IoT & Embedded Systems', 3),
            ('Networking Fundamentals', 2),
            ('Quality Assurance & Software Testing', 3),
            ('Technical Writing', 2),
        ],
    },
    {
        'student_number': '2026-1120',
        'first_name': 'Paolo Miguel',
        'last_name': 'Soriano',
        'email': 'paolo.soriano@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Cybersecurity Fundamentals', 2),
            ('Technical Writing', 3),
            ('Systems Analysis & Documentation', 2),
            ('Data Analysis & Visualization', 2),
        ],
    },
    {
        'student_number': '2026-1121',
        'first_name': 'Katherine Anne',
        'last_name': 'Ong',
        'email': 'katherine.ong@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Systems Analysis & Documentation', 4),
            ('Technical Writing', 3),
            ('Agile Project Management', 3),
            ('Quality Assurance & Software Testing', 2),
        ],
    },
    {
        'student_number': '2026-1124',
        'first_name': 'Ralph Vincent',
        'last_name': 'Alonzo',
        'email': 'ralph.alonzo@bsit.example.edu',
        'course': 'BSIT',
        'section': '3A',
        'year_level': 3,
        'skills': [
            ('Database Design & Management', 3),
            ('Quality Assurance & Software Testing', 4),
            ('Technical Writing', 2),
            ('Systems Analysis & Documentation', 2),
        ],
    },
]

EXISTING_GROUP_PROJECT = 'Student Group Formation and Skill Matching System'
EXISTING_GROUP_NAME = 'Group A'
EXISTING_GROUP_ADDITIONS = ['2026-1103', '2026-1105']

RECONCILE_OBSOLETE_STUDENTS = {
    '2026-1122': ('Miguel Antonio', 'Sy', 'miguel.sy@bsit.example.edu'),
    '2026-1123': ('Lorraine Grace', 'Santiago',
                  'lorraine.santiago@bsit.example.edu'),
    '2026-1125': ('Trisha Marie', 'Tan', 'trisha.tan@bsit.example.edu'),
}
RECONCILE_OBSOLETE_PROJECT = 'University Research Repository Portal'
RECONCILE_MOVED_STUDENTS = ['2026-1121', '2026-1124']
RECONCILE_TARGET_PROJECT = 'Campus Event Management Portal'
RECONCILE_TARGET_GROUP = 'Group A'

GROUPS = [
    {
        'project': 'Campus Event Management Portal',
        'group_name': 'Group A',
        'members': [
            '2026-1101',
            '2026-1102',
            '2026-1104',
            '2026-1121',
            '2026-1124',
        ],
    },
    {
        'project': 'Student Attendance Mobile App',
        'group_name': 'Group A',
        'members': [
            '2026-1106',
            '2026-1107',
            '2026-1108',
            '2026-1109',
            '2026-1110',
        ],
    },
    {
        'project': 'Learning Analytics Dashboard',
        'group_name': 'Group A',
        'members': [
            '2026-1111',
            '2026-1112',
            '2026-1113',
            '2026-1114',
            '2026-1115',
        ],
    },
    {
        'project': 'Smart Campus IoT Monitoring System',
        'group_name': 'Group A',
        'members': [
            '2026-1116',
            '2026-1117',
            '2026-1118',
            '2026-1119',
            '2026-1120',
        ],
    },
]


class Command(BaseCommand):
    help = (
        'Create repeatable sample students, skills, projects, groups, and '
        'memberships. Use --dry-run to preview, --reconcile to apply the '
        'one-time 25-student correction, and --clear to remove only the '
        'sample records created by this command.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview the changes without writing to the database.',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Remove only the sample records created by this command.',
        )
        parser.add_argument(
            '--reconcile',
            action='store_true',
            help=(
                'Apply the one-time correction that removes obsolete sample '
                'records and moves the two retained students into the Campus '
                'Event group before seeding.'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clear = options['clear']
        reconcile = options['reconcile']

        if clear and reconcile:
            raise CommandError(
                'Use either --clear or --reconcile, not both.'
            )

        if clear:
            if dry_run:
                with transaction.atomic():
                    stats = self._clear()
                    transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(
                    'CLEAR PREVIEW - no database changes were committed.'
                ))
            else:
                with transaction.atomic():
                    stats = self._clear()
                self.stdout.write(self.style.SUCCESS(
                    'Sample data removed successfully.'
                ))
            self._print_stats(stats)
            return

        if reconcile:
            if dry_run:
                with transaction.atomic():
                    reconcile_stats = self._reconcile()
                    seed_stats = self._seed(dry_run=True)
                    transaction.set_rollback(True)
                stats = self._merge_stats(reconcile_stats, seed_stats)
                self.stdout.write(self.style.WARNING(
                    'RECONCILE DRY RUN - preview rolled back; no database '
                    'changes were committed.'
                ))
            else:
                with transaction.atomic():
                    reconcile_stats = self._reconcile()
                    seed_stats = self._seed(dry_run=False)
                stats = self._merge_stats(reconcile_stats, seed_stats)
                self.stdout.write(self.style.SUCCESS(
                    'Database reconciled and sample data seeded successfully.'
                ))
            self._print_stats(stats)
            self._print_expected_totals()
            return

        if dry_run:
            stats = self._seed(dry_run=True)
            self.stdout.write(self.style.WARNING(
                'DRY RUN - no database changes were committed.'
            ))
        else:
            with transaction.atomic():
                stats = self._seed(dry_run=False)
            self.stdout.write(self.style.SUCCESS(
                'Sample data seeded successfully.'
            ))
        self._print_stats(stats)

    def _merge_stats(self, *stat_sets):
        merged = defaultdict(int)
        for stats in stat_sets:
            for key, value in stats.items():
                merged[key] += value
        return merged

    def _reconcile(self):
        stats = defaultdict(int)

        original_project = Project.objects.filter(
            project_name=EXISTING_GROUP_PROJECT
        ).first()
        original_group = None
        if original_project is not None:
            original_group = Group.objects.filter(
                project=original_project,
                group_name=EXISTING_GROUP_NAME,
            ).first()

        if original_group is not None:
            for student_number in EXISTING_GROUP_ADDITIONS:
                student = Student.objects.filter(
                    student_number=student_number
                ).first()
                if student is None:
                    continue
                duplicates = GroupMember.objects.filter(
                    student=student
                ).exclude(group=original_group)
                count = duplicates.count()
                if count:
                    stats['reconcile_duplicate_memberships_deleted'] += count
                    duplicates.delete()
        else:
            stats['reconcile_skipped'] += 1

        target_project = Project.objects.filter(
            project_name=RECONCILE_TARGET_PROJECT
        ).first()
        target_group = None
        if target_project is not None:
            target_group = Group.objects.filter(
                project=target_project,
                group_name=RECONCILE_TARGET_GROUP,
            ).first()

        for student_number in RECONCILE_MOVED_STUDENTS:
            student = Student.objects.filter(
                student_number=student_number
            ).first()
            if student is None or target_group is None:
                stats['reconcile_skipped'] += 1
                continue

            old_memberships = GroupMember.objects.filter(
                student=student
            ).exclude(group=target_group)
            count = old_memberships.count()
            if count:
                stats['reconcile_memberships_moved'] += count
                old_memberships.delete()

            membership = GroupMember.objects.filter(
                group=target_group,
                student=student,
            ).first()
            if membership is None:
                stats['reconcile_memberships_created'] += 1
                GroupMember.objects.create(
                    group=target_group,
                    student=student,
                )

        self._remove_obsolete_records(stats)

        return stats

    def _remove_obsolete_records(self, stats):
        obsolete_project = Project.objects.filter(
            project_name=RECONCILE_OBSOLETE_PROJECT
        ).first()
        if obsolete_project is not None:
            for group in Group.objects.filter(project=obsolete_project):
                memberships = GroupMember.objects.filter(group=group)
                count = memberships.count()
                if count:
                    stats['reconcile_group_memberships_deleted'] += count
                    memberships.delete()
                stats['reconcile_groups_deleted'] += 1
                group.delete()

            requirements = ProjectRequiredSkill.objects.filter(
                project=obsolete_project
            )
            count = requirements.count()
            if count:
                stats['reconcile_requirements_deleted'] += count
                requirements.delete()

            stats['reconcile_projects_deleted'] += 1
            obsolete_project.delete()

        for student_number, identity in RECONCILE_OBSOLETE_STUDENTS.items():
            student = Student.objects.filter(
                student_number=student_number
            ).first()
            if student is None:
                continue

            first_name, last_name, email = identity
            if (
                student.first_name != first_name
                or student.last_name != last_name
                or student.email != email
            ):
                raise CommandError(
                    f'Student {student_number} does not match the obsolete '
                    'sample identity. Refusing to delete it.'
                )

            memberships = GroupMember.objects.filter(student=student)
            count = memberships.count()
            if count:
                stats['reconcile_group_memberships_deleted'] += count
                memberships.delete()

            student_skills = StudentSkill.objects.filter(student=student)
            count = student_skills.count()
            if count:
                stats['reconcile_student_skills_deleted'] += count
                student_skills.delete()

            stats['reconcile_students_deleted'] += 1
            student.delete()

    def _seed(self, dry_run):
        stats = defaultdict(int)
        skill_objects = {}
        project_objects = {}
        student_objects = {}

        for skill_name in BASELINE_SKILLS:
            skill = Skill.objects.filter(skill_name=skill_name).first()
            if skill is None:
                raise CommandError(
                    f'Baseline skill "{skill_name}" is missing. Add it before '
                    'seeding the sample data.'
                )
            skill_objects[skill_name] = skill
            stats['baseline_skills'] += 1

        for skill_name, description in NEW_SKILLS.items():
            skill = Skill.objects.filter(skill_name=skill_name).first()
            if skill is not None:
                if (skill.description or '') != description:
                    raise CommandError(
                        f'Skill "{skill_name}" already exists with a different '
                        'description. Refusing to modify an existing skill.'
                    )
                skill_objects[skill_name] = skill
                stats['new_skills_existing'] += 1
            else:
                stats['new_skills_create'] += 1
                if dry_run:
                    skill_objects[skill_name] = None
                else:
                    skill_objects[skill_name] = Skill.objects.create(
                        skill_name=skill_name,
                        description=description,
                    )

        for spec in PROJECTS:
            project = Project.objects.filter(
                project_name=spec['name']
            ).first()
            if project is not None:
                if (project.description or '') != spec['description']:
                    raise CommandError(
                        f'Project "{spec["name"]}" already exists with a '
                        'different description. Refusing to modify an existing '
                        'project.'
                    )
                project_objects[spec['name']] = project
                stats['projects_existing'] += 1
            else:
                stats['projects_create'] += 1
                if dry_run:
                    project_objects[spec['name']] = None
                else:
                    project_objects[spec['name']] = Project.objects.create(
                        project_name=spec['name'],
                        description=spec['description'],
                    )

        for spec in PROJECTS:
            project = project_objects[spec['name']]
            for skill_name, required_level in spec['requirements']:
                skill = skill_objects[skill_name]
                if project is None or skill is None:
                    stats['requirements_create'] += 1
                    continue
                requirement = ProjectRequiredSkill.objects.filter(
                    project=project,
                    skill=skill,
                ).first()
                if requirement is not None:
                    if requirement.required_level != required_level:
                        stats['requirements_update'] += 1
                        if not dry_run:
                            requirement.required_level = required_level
                            requirement.save(update_fields=['required_level'])
                    else:
                        stats['requirements_existing'] += 1
                else:
                    stats['requirements_create'] += 1
                    if not dry_run:
                        ProjectRequiredSkill.objects.create(
                            project=project,
                            skill=skill,
                            required_level=required_level,
                        )

        for spec in STUDENTS:
            student = Student.objects.filter(
                student_number=spec['student_number']
            ).first()
            if student is not None:
                if (
                    student.email != spec['email']
                    or student.first_name != spec['first_name']
                    or student.last_name != spec['last_name']
                ):
                    raise CommandError(
                        f'Student number {spec["student_number"]} already '
                        'belongs to a different student. Refusing to modify '
                        'an existing student.'
                    )
                student_objects[spec['student_number']] = student
                stats['students_existing'] += 1
                updates = {}
                if student.course != spec['course']:
                    updates['course'] = spec['course']
                if student.section != spec['section']:
                    updates['section'] = spec['section']
                if student.year_level != spec['year_level']:
                    updates['year_level'] = spec['year_level']
                if updates:
                    stats['students_update'] += 1
                    if not dry_run:
                        for field, value in updates.items():
                            setattr(student, field, value)
                        student.save(update_fields=list(updates))
            else:
                email_owner = Student.objects.filter(
                    email=spec['email']
                ).exclude(student_number=spec['student_number']).first()
                if email_owner is not None:
                    raise CommandError(
                        f'Email {spec["email"]} already belongs to student '
                        f'{email_owner.student_number}. Refusing to modify an '
                        'existing student.'
                    )
                stats['students_create'] += 1
                if dry_run:
                    student_objects[spec['student_number']] = None
                else:
                    student_objects[spec['student_number']] = (
                        Student.objects.create(
                            student_number=spec['student_number'],
                            first_name=spec['first_name'],
                            last_name=spec['last_name'],
                            email=spec['email'],
                            course=spec['course'],
                            section=spec['section'],
                            year_level=spec['year_level'],
                        )
                    )

        for spec in STUDENTS:
            student = student_objects[spec['student_number']]
            for skill_name, proficiency_level in spec['skills']:
                skill = skill_objects[skill_name]
                if student is None or skill is None:
                    stats['student_skills_create'] += 1
                    continue
                assignment = StudentSkill.objects.filter(
                    student=student,
                    skill=skill,
                ).first()
                if assignment is not None:
                    if assignment.proficiency_level != proficiency_level:
                        stats['student_skills_update'] += 1
                        if not dry_run:
                            assignment.proficiency_level = proficiency_level
                            assignment.save(update_fields=['proficiency_level'])
                    else:
                        stats['student_skills_existing'] += 1
                else:
                    stats['student_skills_create'] += 1
                    if not dry_run:
                        StudentSkill.objects.create(
                            student=student,
                            skill=skill,
                            proficiency_level=proficiency_level,
                        )

        for spec in GROUPS:
            project = project_objects[spec['project']]
            group = None
            if project is not None:
                group = Group.objects.filter(
                    project=project,
                    group_name=spec['group_name'],
                ).first()
            if group is not None:
                stats['groups_existing'] += 1
            else:
                stats['groups_create'] += 1
                if not dry_run:
                    group = Group.objects.create(
                        project=project,
                        group_name=spec['group_name'],
                    )

            for student_number in spec['members']:
                student = student_objects[student_number]
                if group is None or student is None:
                    stats['group_members_create'] += 1
                    continue
                conflict = GroupMember.objects.filter(
                    student=student,
                ).exclude(group=group).first()
                if conflict is not None:
                    raise CommandError(
                        f'Student {student_number} is already assigned to '
                        f'"{conflict.group.group_name}" in project '
                        f'"{conflict.group.project.project_name}". A student '
                        'can belong to only one group in the system.'
                    )
                membership = GroupMember.objects.filter(
                    group=group,
                    student=student,
                ).first()
                if membership is not None:
                    stats['group_members_existing'] += 1
                else:
                    stats['group_members_create'] += 1
                    if not dry_run:
                        GroupMember.objects.create(
                            group=group,
                            student=student,
                        )

        self._augment_existing_group(dry_run, stats, student_objects)

        return stats

    def _augment_existing_group(self, dry_run, stats, student_objects):
        project = Project.objects.filter(
            project_name=EXISTING_GROUP_PROJECT
        ).first()
        if project is None:
            stats['existing_group_skipped'] += 1
            return

        group = Group.objects.filter(
            project=project,
            group_name=EXISTING_GROUP_NAME,
        ).first()
        if group is None:
            stats['existing_group_skipped'] += 1
            return

        current_members = GroupMember.objects.filter(group=group).count()
        for student_number in EXISTING_GROUP_ADDITIONS:
            student = student_objects.get(student_number)
            if student is None:
                stats['existing_group_members_skipped'] += 1
                continue

            membership = GroupMember.objects.filter(
                group=group,
                student=student,
            ).first()
            if membership is not None:
                stats['existing_group_members_existing'] += 1
                continue

            conflict = GroupMember.objects.filter(
                student=student,
            ).exclude(group=group).first()
            if conflict is not None:
                raise CommandError(
                    f'Student {student_number} is already assigned to '
                    f'"{conflict.group.group_name}" in project '
                    f'"{conflict.group.project.project_name}". A student '
                    'can belong to only one group in the system.'
                )

            if current_members >= 5:
                stats['existing_group_members_skipped'] += 1
                continue

            stats['existing_group_members_create'] += 1
            if not dry_run:
                GroupMember.objects.create(group=group, student=student)
            current_members += 1

    def _clear(self):
        stats = defaultdict(int)
        skill_objects = {}
        project_objects = {}
        student_objects = {}

        self._remove_obsolete_records(stats)

        for skill_name, description in NEW_SKILLS.items():
            skill = Skill.objects.filter(skill_name=skill_name).first()
            if skill is not None and (skill.description or '') == description:
                skill_objects[skill_name] = skill
            elif skill is not None:
                stats['skipped_skills'] += 1

        for spec in PROJECTS:
            project = Project.objects.filter(
                project_name=spec['name']
            ).first()
            if project is not None and (
                (project.description or '') == spec['description']
            ):
                project_objects[spec['name']] = project
            elif project is not None:
                stats['skipped_projects'] += 1

        for spec in STUDENTS:
            student = Student.objects.filter(
                student_number=spec['student_number']
            ).first()
            if student is not None and student.email == spec['email']:
                student_objects[spec['student_number']] = student
            elif student is not None:
                stats['skipped_students'] += 1

        sample_groups = []
        for spec in GROUPS:
            project = project_objects.get(spec['project'])
            if project is None:
                continue
            group = Group.objects.filter(
                project=project,
                group_name=spec['group_name'],
            ).first()
            if group is not None:
                sample_groups.append((spec, group))

        for spec, group in sample_groups:
            for student_number in spec['members']:
                student = student_objects.get(student_number)
                if student is None:
                    continue
                membership = GroupMember.objects.filter(
                    group=group,
                    student=student,
                )
                count = membership.count()
                if count:
                    stats['group_members_deleted'] += count
                    membership.delete()

        self._clear_group_a_additions(stats, student_objects)

        for spec, group in sample_groups:
            if GroupMember.objects.filter(group=group).exists():
                stats['skipped_groups'] += 1
                continue
            stats['groups_deleted'] += 1
            group.delete()

        for spec in PROJECTS:
            project = project_objects.get(spec['name'])
            if project is None:
                continue
            for skill_name, _ in spec['requirements']:
                skill = skill_objects.get(skill_name)
                if skill is None:
                    skill = Skill.objects.filter(
                        skill_name=skill_name
                    ).first()
                if skill is None:
                    continue
                requirement = ProjectRequiredSkill.objects.filter(
                    project=project,
                    skill=skill,
                )
                count = requirement.count()
                if count:
                    stats['requirements_deleted'] += count
                    requirement.delete()

        for spec in PROJECTS:
            project = project_objects.get(spec['name'])
            if project is None:
                continue
            if (
                Group.objects.filter(project=project).exists()
                or ProjectRequiredSkill.objects.filter(project=project).exists()
            ):
                stats['skipped_projects'] += 1
                continue
            stats['projects_deleted'] += 1
            project.delete()

        for spec in STUDENTS:
            student = student_objects.get(spec['student_number'])
            if student is None:
                continue
            for skill_name, _ in spec['skills']:
                skill = skill_objects.get(skill_name)
                if skill is None:
                    skill = Skill.objects.filter(
                        skill_name=skill_name
                    ).first()
                if skill is None:
                    continue
                assignment = StudentSkill.objects.filter(
                    student=student,
                    skill=skill,
                )
                count = assignment.count()
                if count:
                    stats['student_skills_deleted'] += count
                    assignment.delete()

        for spec in STUDENTS:
            student = student_objects.get(spec['student_number'])
            if student is None:
                continue
            if (
                StudentSkill.objects.filter(student=student).exists()
                or GroupMember.objects.filter(student=student).exists()
            ):
                stats['skipped_students'] += 1
                continue
            stats['students_deleted'] += 1
            student.delete()

        for skill in skill_objects.values():
            if (
                StudentSkill.objects.filter(skill=skill).exists()
                or ProjectRequiredSkill.objects.filter(skill=skill).exists()
            ):
                stats['skipped_skills'] += 1
                continue
            stats['skills_deleted'] += 1
            skill.delete()

        return stats

    def _clear_group_a_additions(self, stats, student_objects):
        for student_number in EXISTING_GROUP_ADDITIONS:
            student = student_objects.get(student_number)
            if student is None:
                continue
            memberships = GroupMember.objects.filter(student=student)
            count = memberships.count()
            if count:
                stats['existing_group_members_deleted'] += count
                memberships.delete()

    def _print_stats(self, stats):
        labels = [
            ('baseline_skills', 'Baseline skills reused'),
            ('new_skills_existing', 'Sample skills already present'),
            ('new_skills_create', 'Sample skills to create'),
            ('projects_existing', 'Sample projects already present'),
            ('projects_create', 'Sample projects to create'),
            ('requirements_existing', 'Requirements already present'),
            ('requirements_update', 'Requirements to update'),
            ('requirements_create', 'Requirements to create'),
            ('students_existing', 'Sample students already present'),
            ('students_update', 'Sample students to update'),
            ('students_create', 'Sample students to create'),
            ('student_skills_existing', 'Student-skill rows already present'),
            ('student_skills_update', 'Student-skill rows to update'),
            ('student_skills_create', 'Student-skill rows to create'),
            ('groups_existing', 'Sample groups already present'),
            ('groups_create', 'Sample groups to create'),
            ('group_members_existing', 'Group memberships already present'),
            ('group_members_create', 'Group memberships to create'),
            ('existing_group_members_existing',
             'Existing Group A sample members already present'),
            ('existing_group_members_create',
             'Existing Group A sample members to add'),
            ('existing_group_members_skipped',
             'Existing Group A sample members skipped'),
            ('existing_group_skipped', 'Existing Group A skipped'),
            ('existing_group_members_deleted',
             'Existing Group A sample members deleted'),
            ('group_members_deleted', 'Sample group memberships deleted'),
            ('groups_deleted', 'Sample groups deleted'),
            ('requirements_deleted', 'Sample requirements deleted'),
            ('student_skills_deleted', 'Sample student-skill rows deleted'),
            ('students_deleted', 'Sample students deleted'),
            ('skills_deleted', 'Sample skills deleted'),
            ('skipped_projects', 'Projects skipped (in use or changed)'),
            ('skipped_groups', 'Groups skipped (still have members)'),
            ('skipped_students', 'Students skipped (still referenced)'),
            ('skipped_skills', 'Skills skipped (still referenced)'),
            ('reconcile_duplicate_memberships_deleted',
             'Duplicate sample memberships removed'),
            ('reconcile_memberships_moved',
             'Sample memberships moved'),
            ('reconcile_memberships_created',
             'Replacement sample memberships created'),
            ('reconcile_group_memberships_deleted',
             'Obsolete group memberships removed'),
            ('reconcile_groups_deleted', 'Obsolete sample groups removed'),
            ('reconcile_requirements_deleted',
             'Obsolete project requirements removed'),
            ('reconcile_projects_deleted', 'Obsolete sample projects removed'),
            ('reconcile_student_skills_deleted',
             'Obsolete student-skill rows removed'),
            ('reconcile_students_deleted', 'Obsolete sample students removed'),
            ('reconcile_skipped', 'Reconciliation items skipped'),
        ]
        for key, label in labels:
            value = stats.get(key, 0)
            if value:
                self.stdout.write(f'  {label}: {value}')

        self.stdout.write('')
        self.stdout.write('Planned sample totals:')
        self.stdout.write(
            f'  Students: {len(STUDENTS)}  |  Groups: {len(GROUPS)}  |  '
            f'Projects: {len(PROJECTS)}  |  New skills: {len(NEW_SKILLS)}'
        )
        self.stdout.write(
            f'  Student skills: {sum(len(s["skills"]) for s in STUDENTS)}  |  '
            f'Requirements: {sum(len(p["requirements"]) for p in PROJECTS)}  |  '
            f'Memberships: {sum(len(g["members"]) for g in GROUPS)}'
        )

    def _print_expected_totals(self):
        sample_numbers = [spec['student_number'] for spec in STUDENTS]
        obsolete_numbers = list(RECONCILE_OBSOLETE_STUDENTS)
        real_students = Student.objects.exclude(
            student_number__in=sample_numbers + obsolete_numbers
        )
        real_student_count = real_students.count()
        real_student_skills = StudentSkill.objects.filter(
            student__in=real_students
        ).count()

        sample_project_names = [spec['name'] for spec in PROJECTS]
        original_projects = Project.objects.exclude(
            project_name__in=sample_project_names + [RECONCILE_OBSOLETE_PROJECT]
        ).count()
        original_groups = Group.objects.exclude(
            project__project_name__in=(
                sample_project_names + [RECONCILE_OBSOLETE_PROJECT]
            )
        ).count()

        original_project = Project.objects.filter(
            project_name=EXISTING_GROUP_PROJECT
        ).first()
        original_requirements = 0
        original_group_members = 0
        if original_project is not None:
            original_requirements = ProjectRequiredSkill.objects.filter(
                project=original_project
            ).count()
            original_group = Group.objects.filter(
                project=original_project,
                group_name=EXISTING_GROUP_NAME,
            ).first()
            if original_group is not None:
                original_group_members = GroupMember.objects.filter(
                    group=original_group
                ).exclude(
                    student__student_number__in=EXISTING_GROUP_ADDITIONS
                ).count()

        current_skill_names = set(
            Skill.objects.values_list('skill_name', flat=True)
        )
        missing_new_skills = [
            name for name in NEW_SKILLS if name not in current_skill_names
        ]

        final_students = real_student_count + len(STUDENTS)
        final_skills = len(current_skill_names) + len(missing_new_skills)
        final_student_skills = (
            real_student_skills
            + sum(len(spec['skills']) for spec in STUDENTS)
        )
        final_projects = original_projects + len(PROJECTS)
        final_requirements = (
            original_requirements
            + sum(len(spec['requirements']) for spec in PROJECTS)
        )
        final_groups = original_groups + len(GROUPS)
        final_memberships = (
            original_group_members
            + len(EXISTING_GROUP_ADDITIONS)
            + sum(len(spec['members']) for spec in GROUPS)
        )

        self.stdout.write('')
        self.stdout.write('Expected final database totals:')
        self.stdout.write(f'  Students: {final_students}')
        self.stdout.write(f'  Skills: {final_skills}')
        self.stdout.write(f'  Student skills: {final_student_skills}')
        self.stdout.write(f'  Projects: {final_projects}')
        self.stdout.write(f'  Project required skills: {final_requirements}')
        self.stdout.write(f'  Groups: {final_groups}')
        self.stdout.write(f'  Group memberships: {final_memberships}')
        self.stdout.write('')
        self.stdout.write('Expected final group sizes:')
        self.stdout.write(
            f'  {EXISTING_GROUP_PROJECT} / {EXISTING_GROUP_NAME}: '
            f'{original_group_members + len(EXISTING_GROUP_ADDITIONS)}'
        )
        for spec in GROUPS:
            self.stdout.write(
                f'  {spec["project"]} / {spec["group_name"]}: '
                f'{len(spec["members"])}'
            )

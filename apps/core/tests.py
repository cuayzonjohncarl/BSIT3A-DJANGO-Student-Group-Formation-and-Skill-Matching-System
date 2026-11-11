from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.core.roles import (
    can_manage,
    is_admin,
    role_for,
    role_label,
    set_role,
)
from apps.students.models import (
    Group,
    GroupMember,
    Project,
    ProjectRequiredSkill,
    Skill,
    Student,
    StudentSkill,
)
from apps.students.tests import UnmanagedTablesMixin


class HomeViewTests(UnmanagedTablesMixin, TransactionTestCase):
    """The dashboard reads the unmanaged student/skill/project/group tables.

    Those tables are never created by migrations, so the test database has to
    create them explicitly (see ``UnmanagedTablesMixin``). Without that, the
    dashboard queries fail with "no such table".
    """

    def _login(self, username='dashboard_user'):
        user = get_user_model().objects.create_user(
            username=username, password='secret1234'
        )
        self.client.force_login(user)
        return user

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)

    def test_home_renders_for_authenticated_user(self):
        self._login()

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_reports_real_skill_coverage(self):
        """Dashboard aggregates come from real records, not estimates."""
        self._login()

        student = Student.objects.create(
            student_number='2026-0001',
            first_name='Juan',
            last_name='Dela Cruz',
            email='juan@example.com',
            course='BSIT',
            section='A',
            year_level=3,
        )
        skill = Skill.objects.create(skill_name='Python')
        StudentSkill.objects.create(
            student=student, skill=skill, proficiency_level=4
        )

        project = Project.objects.create(project_name='Capstone')
        ProjectRequiredSkill.objects.create(
            project=project, skill=skill, required_level=3
        )

        group = Group.objects.create(group_name='Team A', project=project)
        GroupMember.objects.create(group=group, student=student)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_students'], 1)
        self.assertEqual(response.context['total_projects'], 1)
        self.assertEqual(response.context['total_groups'], 1)
        self.assertEqual(response.context['students_with_skills'], 1)
        self.assertEqual(response.context['total_requirements'], 1)
        self.assertEqual(response.context['checks_total'], 1)
        self.assertEqual(response.context['satisfied_total'], 1)
        self.assertEqual(response.context['deficient_total'], 0)
        self.assertEqual(response.context['missing_total'], 0)
        self.assertEqual(response.context['coverage_pct'], 100)
        self.assertEqual(response.context['avg_match_pct'], 100)
        self.assertEqual(response.context['full_match_groups'], 1)

    def test_home_handles_empty_database(self):
        """No groups or requirements: coverage stays empty instead of faking 0%."""
        self._login()

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['coverage_pct'])
        self.assertIsNone(response.context['avg_match_pct'])
        self.assertEqual(response.context['checks_total'], 0)
        self.assertEqual(response.context['analyzed_recent'], [])


# ---------------------------------------------------------------------------
# Stage 7 - role-based authorization (concept paper objective 6)
# ---------------------------------------------------------------------------

class RoleResolutionTests(TestCase):
    """Roles are stored in the built-in auth groups, so no schema change is needed."""

    def setUp(self):
        self.User = get_user_model()

    def test_superuser_is_always_administrator(self):
        user = self.User.objects.create_superuser('root', password='secret1234')
        self.assertEqual(role_for(user), 'admin')
        self.assertTrue(is_admin(user))
        self.assertTrue(can_manage(user))

    def test_user_without_role_group_defaults_to_instructor(self):
        """Accounts created before roles existed keep their previous access."""
        user = self.User.objects.create_user('legacy', password='secret1234')
        self.assertEqual(role_for(user), 'instructor')
        self.assertTrue(can_manage(user))
        self.assertFalse(is_admin(user))

    def test_role_groups_are_resolved_in_priority_order(self):
        user = self.User.objects.create_user('multi', password='secret1234')
        set_role(user, 'student')
        self.assertEqual(role_for(user), 'student')
        set_role(user, 'instructor')
        self.assertEqual(role_for(user), 'instructor')
        set_role(user, 'admin')
        self.assertEqual(role_for(user), 'admin')

    def test_set_role_moves_the_user_between_groups(self):
        user = self.User.objects.create_user('mover', password='secret1234')
        set_role(user, 'student')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['Student'])
        set_role(user, 'instructor')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['Instructor'])

    def test_set_role_rejects_unknown_roles(self):
        user = self.User.objects.create_user('odd', password='secret1234')
        with self.assertRaises(ValueError):
            set_role(user, 'robot')

    def test_anonymous_user_has_no_role(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertIsNone(role_for(AnonymousUser()))
        self.assertIsNone(role_for(None))
        self.assertFalse(can_manage(AnonymousUser()))

    def test_role_label_matches_role(self):
        user = self.User.objects.create_user('labelled', password='secret1234')
        set_role(user, 'student')
        self.assertEqual(role_label(user), 'Student')


class RolePermissionTests(TestCase):
    """Authorization is enforced in the views, not by hiding buttons."""

    def setUp(self):
        self.User = get_user_model()
        self.admin = self.User.objects.create_superuser('boss', password='secret1234')
        self.instructor = self.User.objects.create_user('teach', password='secret1234')
        set_role(self.instructor, 'instructor')
        self.student = self.User.objects.create_user('learner', password='secret1234')
        set_role(self.student, 'student')

    def test_users_page_is_admin_only(self):
        self.client.force_login(self.instructor)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/home/')

        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse('users:user_list')).status_code, 200
        )

    def test_user_save_ajax_rejects_non_administrators(self):
        self.client.force_login(self.instructor)
        response = self.client.post(
            reverse('users:user_save_ajax'),
            {'username': 'newbie', 'password': 'secret1234', 'role': 'admin'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.User.objects.filter(username='newbie').exists())

    def test_user_save_ajax_validates_the_role(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('users:user_save_ajax'),
            {'username': 'newbie', 'password': 'secret1234', 'role': 'wizard'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('role', response.json()['error'].lower())

    def test_user_save_ajax_assigns_the_requested_role(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('users:user_save_ajax'),
            {
                'username': 'newbie',
                'password': 'secret1234',
                'email': 'newbie@example.com',
                'role': 'student',
                'is_active': 'true',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['role'], 'student')
        self.assertEqual(role_for(self.User.objects.get(username='newbie')), 'student')

    def test_registration_creates_a_student_account(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'fresh',
                'first_name': 'Fresh',
                'last_name': 'Learner',
                'email': 'fresh@example.com',
                'password': 'S0meStr0ngPass!',
                'confirm_password': 'S0meStr0ngPass!',
            },
        )
        self.assertEqual(response.status_code, 302)
        user = self.User.objects.get(username='fresh')
        self.assertEqual(role_for(user), 'student')
        self.assertFalse(can_manage(user))

    def test_registration_rejects_weak_passwords(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'weakling',
                'first_name': 'Weak',
                'last_name': 'Password',
                'email': 'weak@example.com',
                'password': 'short',
                'confirm_password': 'short',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.User.objects.filter(username='weakling').exists())


# ---------------------------------------------------------------------------
# Stage 7 - dashboard analytics series
# ---------------------------------------------------------------------------

@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed chart tests run only with mysite.test_settings (SQLite).',
)
class DashboardChartTests(UnmanagedTablesMixin, TransactionTestCase):
    """Every chart series must be a real database aggregate."""

    def _login(self):
        user = get_user_model().objects.create_user('chartuser', password='secret1234')
        self.client.force_login(user)

    def test_proficiency_chart_counts_every_assignment(self):
        self._login()
        skill_a = Skill.objects.create(skill_name='Python')
        skill_b = Skill.objects.create(skill_name='Django')
        student = Student.objects.create(
            student_number='2026-1', first_name='Ada', last_name='Lovelace',
            email='ada@example.com', course='BSIT', section='A', year_level=3,
        )
        StudentSkill.objects.create(student=student, skill=skill_a, proficiency_level=5)
        StudentSkill.objects.create(student=student, skill=skill_b, proficiency_level=2)

        response = self.client.get(reverse('dashboard'))
        chart = response.context['proficiency_chart']

        self.assertEqual([row['label'] for row in chart], [
            'Beginner', 'Elementary', 'Intermediate', 'Advanced', 'Expert',
        ])
        self.assertEqual([row['count'] for row in chart], [0, 1, 0, 0, 1])

    def test_course_chart_groups_by_course_not_by_student(self):
        """Regression: the model's default ordering must not leak into GROUP BY."""
        self._login()
        for index, course in enumerate(['BSIT', 'BSIT', 'BSIT', 'BSCS'], start=1):
            Student.objects.create(
                student_number=f'2026-{index}', first_name=f'Stud{index}',
                last_name=f'Ent{index}', email=f'stud{index}@example.com',
                course=course, section='A', year_level=1,
            )

        response = self.client.get(reverse('dashboard'))
        chart = response.context['course_chart']

        self.assertEqual(len(chart), 2)
        self.assertEqual(chart[0], {'label': 'BSIT', 'value': 3})
        self.assertEqual(chart[1], {'label': 'BSCS', 'value': 1})

    def test_requirement_status_and_group_series_match_the_analysis(self):
        self._login()
        skill = Skill.objects.create(skill_name='Python')
        project = Project.objects.create(project_name='Capstone')
        ProjectRequiredSkill.objects.create(project=project, skill=skill, required_level=3)
        student = Student.objects.create(
            student_number='2026-9', first_name='Grace', last_name='Hopper',
            email='grace@example.com', course='BSIT', section='A', year_level=4,
        )
        group = Group.objects.create(project=project, group_name='Team A')
        GroupMember.objects.create(group=group, student=student)

        response = self.client.get(reverse('dashboard'))
        status_chart = response.context['requirement_status_chart']
        group_chart = response.context['group_match_series']

        # The member has no proficiency recorded, so the requirement is missing.
        self.assertEqual(status_chart, [
            {'label': 'Satisfied', 'value': 0},
            {'label': 'Deficient', 'value': 0},
            {'label': 'Missing', 'value': 1},
        ])
        self.assertEqual(group_chart, [{'label': 'Team A', 'value': 0}])
        self.assertEqual(response.context['checks_total'], 1)

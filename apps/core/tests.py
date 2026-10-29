from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import reverse

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

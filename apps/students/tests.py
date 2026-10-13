from unittest import skipUnless

from django.contrib.auth.models import User
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import resolve, reverse

from .models import (
    Group,
    GroupMember,
    Project,
    ProjectRequiredSkill,
    Skill,
    Student,
    StudentSkill,
)
from .views import _parse_proficiency


class ModelTableMappingTests(SimpleTestCase):
    """Verify each model maps onto the pre-existing MariaDB/MySQL table design."""

    EXPECTED = {
        Student: ('students', 'student_id'),
        Skill: ('skills', 'skill_id'),
        StudentSkill: ('student_skills', 'student_skill_id'),
        Project: ('projects', 'project_id'),
        ProjectRequiredSkill: ('project_required_skills', 'project_skill_id'),
        Group: ('groups', 'group_id'),
        GroupMember: ('group_members', 'group_member_id'),
    }

    def test_db_table_and_primary_key_column(self):
        for model, (table, pk_column) in self.EXPECTED.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.db_table, table)
                pk = model._meta.pk
                self.assertEqual(pk.column, pk_column)
                self.assertEqual(pk.get_internal_type(), 'AutoField')

    def test_tables_are_django_unmanaged(self):
        for model in self.EXPECTED:
            with self.subTest(model=model.__name__):
                self.assertIs(model._meta.managed, False)


class ForeignKeyMappingTests(SimpleTestCase):
    """Verify foreign-key columns and their target models match the design."""

    def _assert_fk(self, model, column, target):
        field = model._meta.get_field(column)
        self.assertEqual(field.column, column)
        self.assertEqual(field.get_internal_type(), 'ForeignKey')
        self.assertIs(field.related_model, target)

    def test_student_skill_foreign_keys(self):
        self._assert_fk(StudentSkill, 'student_id', Student)
        self._assert_fk(StudentSkill, 'skill_id', Skill)

    def test_project_required_skill_foreign_keys(self):
        self._assert_fk(ProjectRequiredSkill, 'project_id', Project)
        self._assert_fk(ProjectRequiredSkill, 'skill_id', Skill)

    def test_group_foreign_keys(self):
        self._assert_fk(Group, 'project_id', Project)

    def test_group_member_foreign_keys(self):
        self._assert_fk(GroupMember, 'group_id', Group)
        self._assert_fk(GroupMember, 'student_id', Student)


class FieldShapeTests(SimpleTestCase):
    """Verify column types and nullability match the schema in DATABASE_DESIGN.md."""

    def _assert_field(self, model, name, internal_type, max_length=None,
                      null=False, blank=False):
        field = model._meta.get_field(name)
        self.assertEqual(field.get_internal_type(), internal_type, name)
        if max_length is not None:
            self.assertEqual(field.max_length, max_length)
        self.assertEqual(field.null, null, name)
        self.assertEqual(field.blank, blank, name)

    def test_skill_fields(self):
        self._assert_field(Skill, 'skill_name', 'CharField', max_length=100)
        self._assert_field(Skill, 'description', 'TextField', null=True, blank=True)

    def test_student_skill_fields(self):
        self._assert_field(StudentSkill, 'proficiency_level', 'IntegerField')

    def test_project_fields(self):
        self._assert_field(Project, 'project_name', 'CharField', max_length=255)
        self._assert_field(Project, 'description', 'TextField', null=True, blank=True)
        created = Project._meta.get_field('created_at')
        self.assertEqual(created.get_internal_type(), 'DateTimeField')
        self.assertTrue(created.auto_now_add)

    def test_project_required_skill_fields(self):
        self._assert_field(ProjectRequiredSkill, 'required_level', 'IntegerField')

    def test_group_fields(self):
        self._assert_field(Group, 'group_name', 'CharField', max_length=255)
        created = Group._meta.get_field('created_at')
        self.assertEqual(created.get_internal_type(), 'DateTimeField')
        self.assertTrue(created.auto_now_add)


class StringMethodTests(SimpleTestCase):
    """Smoke-test __str__ representations without touching the database."""

    def _student(self):
        return Student(
            student_id=1,
            student_number='2023-0001',
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            course='BSIT',
            section='3A',
        )

    def test_simple_str_methods(self):
        skill = Skill(skill_id=1, skill_name='Python')
        project = Project(project_id=1, project_name='Website')
        group = Group(group_id=1, group_name='Alpha')
        self.assertEqual(str(skill), 'Python')
        self.assertEqual(str(project), 'Website')
        self.assertEqual(str(group), 'Alpha')

    def test_junction_str_methods(self):
        student = self._student()
        skill = Skill(skill_id=1, skill_name='Python')
        project = Project(project_id=1, project_name='Website')
        group = Group(group_id=1, group_name='Alpha')

        student_skill = StudentSkill(student=student, skill=skill, proficiency_level=5)
        required = ProjectRequiredSkill(project=project, skill=skill, required_level=3)
        member = GroupMember(group=group, student=student)

        self.assertEqual(str(student_skill), 'Doe, Jane (2023-0001) - Python (5)')
        self.assertEqual(str(required), 'Website - Python (3)')
        self.assertEqual(str(member), 'Alpha - Doe, Jane (2023-0001)')


class Stage2UrlResolutionTests(SimpleTestCase):
    """Verify the Stage 2 skill and student-skill routes are wired up."""

    EXPECTED = {
        '/students/skills/': 'students:skill_list',
        '/students/skills/ajax/list/': 'students:skill_list_ajax',
        '/students/skills/ajax/get/1/': 'students:skill_get_ajax',
        '/students/skills/ajax/save/': 'students:skill_save_ajax',
        '/students/skills/ajax/delete/1/': 'students:skill_delete_ajax',
        '/students/student-skills/': 'students:student_skill_list',
        '/students/student-skills/ajax/list/': 'students:student_skill_list_ajax',
        '/students/student-skills/ajax/get/1/': 'students:student_skill_get_ajax',
        '/students/student-skills/ajax/save/': 'students:student_skill_save_ajax',
        '/students/student-skills/ajax/delete/1/': 'students:student_skill_delete_ajax',
    }

    def test_paths_resolve_to_expected_view_names(self):
        for path, view_name in self.EXPECTED.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).view_name, view_name)

    def test_named_urls_reverse(self):
        self.assertEqual(reverse('students:skill_list'), '/students/skills/')
        self.assertEqual(
            reverse('students:skill_save_ajax'), '/students/skills/ajax/save/'
        )
        self.assertEqual(reverse('students:student_skill_list'), '/students/student-skills/')
        self.assertEqual(
            reverse('students:student_skill_save_ajax'),
            '/students/student-skills/ajax/save/',
        )


class Stage2ProficiencyParsingTests(SimpleTestCase):
    """The proficiency parser accepts integers only; the schema has no range."""

    def test_valid_integers(self):
        for raw, expected in [('5', 5), ('0', 0), ('42', 42), ('-3', -3)]:
            with self.subTest(raw=raw):
                self.assertEqual(_parse_proficiency(raw), expected)

    def test_invalid_values_return_none(self):
        for raw in ['', '   ', 'abc', '3.5', None, '1e3']:
            with self.subTest(raw=raw):
                self.assertIsNone(_parse_proficiency(raw))


class Stage2LoginRequiredTests(TestCase):
    """Every Stage 2 endpoint must require authentication."""

    def test_anonymous_get_redirects_to_login(self):
        for url in [
            reverse('students:skill_list'),
            reverse('students:student_skill_list'),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('next=', response['Location'])

    def test_anonymous_post_redirects_to_login(self):
        for url in [
            reverse('students:skill_save_ajax'),
            reverse('students:skill_delete_ajax', args=[1]),
            reverse('students:student_skill_save_ajax'),
            reverse('students:student_skill_delete_ajax', args=[1]),
        ]:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('next=', response['Location'])


class UnmanagedTablesMixin:
    """Create the real (unmanaged) table shapes inside the throwaway test DB.

    The models are declared with ``managed = False`` so Django's test runner
    never creates their tables. These helpers create/drop the tables only in
    the test database, never in the live MariaDB/MySQL database.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(Student)
            editor.create_model(Skill)
            editor.create_model(Project)
            editor.create_model(StudentSkill)
            editor.create_model(ProjectRequiredSkill)
            editor.create_model(Group)
            editor.create_model(GroupMember)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(GroupMember)
            editor.delete_model(Group)
            editor.delete_model(ProjectRequiredSkill)
            editor.delete_model(StudentSkill)
            editor.delete_model(Project)
            editor.delete_model(Skill)
            editor.delete_model(Student)
        super().tearDownClass()


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed Stage 2 tests run only with mysite.test_settings (SQLite).',
)
class Stage2CrudTests(UnmanagedTablesMixin, TransactionTestCase):
    """Exercise the Stage 2 create/read/update/delete flows on SQLite."""

    def setUp(self):
        # TransactionTestCase flushes managed (Django) tables between tests but
        # not the unmanaged tables, so clear them explicitly for isolation.
        StudentSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        ProjectRequiredSkill.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        Skill.objects.all().delete()
        Student.objects.all().delete()

        self.user = User.objects.create_user(username='tester', password='secret123')
        self.client.force_login(self.user)
        self.student = Student.objects.create(
            student_number='2023-0001',
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            course='BSIT',
            section='3A',
        )

    # -- Helpers ------------------------------------------------------------

    def _create_skill(self, name='Python', description='A language'):
        return Skill.objects.create(skill_name=name, description=description)

    def _save_skill(self, **data):
        return self.client.post(reverse('students:skill_save_ajax'), data)

    # -- Skills CRUD --------------------------------------------------------

    def test_create_skill(self):
        response = self._save_skill(skill_name='Python', description='A language')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(Skill.objects.filter(skill_name='Python').exists())

    def test_create_skill_requires_name(self):
        response = self._save_skill(skill_name='   ', description='x')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertEqual(Skill.objects.count(), 0)

    def test_duplicate_skill_name_is_rejected_case_insensitively(self):
        self._create_skill(name='Python')
        response = self._save_skill(skill_name='python')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Skill.objects.filter(skill_name__iexact='python').count(), 1)

    def test_edit_skill(self):
        skill = self._create_skill(name='Python')
        response = self._save_skill(
            skill_id=str(skill.pk), skill_name='Python 3', description='updated'
        )
        self.assertEqual(response.status_code, 200)
        skill.refresh_from_db()
        self.assertEqual(skill.skill_name, 'Python 3')
        self.assertEqual(skill.description, 'updated')

    def test_edit_skill_keeps_same_name(self):
        skill = self._create_skill(name='Python')
        response = self._save_skill(skill_id=str(skill.pk), skill_name='Python')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Skill.objects.count(), 1)

    def test_delete_skill(self):
        skill = self._create_skill()
        response = self.client.post(
            reverse('students:skill_delete_ajax', args=[skill.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Skill.objects.filter(pk=skill.pk).exists())

    def test_delete_skill_in_use_is_blocked(self):
        skill = self._create_skill()
        StudentSkill.objects.create(
            student=self.student, skill=skill, proficiency_level=3
        )
        response = self.client.post(
            reverse('students:skill_delete_ajax', args=[skill.pk])
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())

    # -- Student-skill CRUD -------------------------------------------------

    def _save_assignment(self, **data):
        return self.client.post(reverse('students:student_skill_save_ajax'), data)

    def test_assign_skill_to_student(self):
        skill = self._create_skill()
        response = self._save_assignment(
            student_id=str(self.student.pk), skill_id=str(skill.pk),
            proficiency_level='4',
        )
        self.assertEqual(response.status_code, 200)
        assignment = StudentSkill.objects.get()
        self.assertEqual(assignment.student_id, self.student.pk)
        self.assertEqual(assignment.skill_id, skill.pk)
        self.assertEqual(assignment.proficiency_level, 4)

    def test_assignment_requires_student_and_skill(self):
        skill = self._create_skill()
        missing_student = self._save_assignment(
            skill_id=str(skill.pk), proficiency_level='4'
        )
        missing_skill = self._save_assignment(
            student_id=str(self.student.pk), proficiency_level='4'
        )
        self.assertEqual(missing_student.status_code, 400)
        self.assertEqual(missing_skill.status_code, 400)
        self.assertEqual(StudentSkill.objects.count(), 0)

    def test_assignment_requires_integer_proficiency(self):
        skill = self._create_skill()
        response = self._save_assignment(
            student_id=str(self.student.pk), skill_id=str(skill.pk),
            proficiency_level='expert',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudentSkill.objects.count(), 0)

    def test_assignment_rejects_non_numeric_ids(self):
        response = self._save_assignment(
            student_id='abc', skill_id='xyz', proficiency_level='3'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertEqual(StudentSkill.objects.count(), 0)

    def test_duplicate_assignment_is_rejected(self):
        skill = self._create_skill()
        StudentSkill.objects.create(
            student=self.student, skill=skill, proficiency_level=2
        )
        response = self._save_assignment(
            student_id=str(self.student.pk), skill_id=str(skill.pk),
            proficiency_level='5',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudentSkill.objects.count(), 1)

    def test_edit_assignment_proficiency(self):
        skill = self._create_skill()
        assignment = StudentSkill.objects.create(
            student=self.student, skill=skill, proficiency_level=2
        )
        response = self._save_assignment(
            student_skill_id=str(assignment.pk),
            student_id=str(self.student.pk),
            skill_id=str(skill.pk),
            proficiency_level='5',
        )
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.proficiency_level, 5)

    def test_delete_assignment(self):
        skill = self._create_skill()
        assignment = StudentSkill.objects.create(
            student=self.student, skill=skill, proficiency_level=2
        )
        response = self.client.post(
            reverse('students:student_skill_delete_ajax', args=[assignment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StudentSkill.objects.count(), 0)

    def test_assignment_list_and_get_endpoints(self):
        skill = self._create_skill()
        assignment = StudentSkill.objects.create(
            student=self.student, skill=skill, proficiency_level=2
        )
        list_response = self.client.get(reverse('students:student_skill_list_ajax'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()['total'], 1)

        get_response = self.client.get(
            reverse('students:student_skill_get_ajax', args=[assignment.pk])
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()['skill_name'], skill.skill_name)

    def test_skill_list_and_get_endpoints(self):
        skill = self._create_skill(name='Django')
        list_response = self.client.get(reverse('students:skill_list_ajax'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()['total'], 1)

        search_response = self.client.get(
            reverse('students:skill_list_ajax'), {'q': 'djan'}
        )
        self.assertEqual(search_response.json()['total'], 1)

        get_response = self.client.get(
            reverse('students:skill_get_ajax', args=[skill.pk])
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()['skill_name'], 'Django')

    def test_delete_skill_required_by_project_is_blocked(self):
        skill = self._create_skill()
        project = Project.objects.create(project_name='Capstone')
        ProjectRequiredSkill.objects.create(
            project=project, skill=skill, required_level=3
        )
        response = self.client.post(
            reverse('students:skill_delete_ajax', args=[skill.pk])
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Skill.objects.filter(pk=skill.pk).exists())

    def test_skill_list_page_renders(self):
        self._create_skill(name='Rendered Skill')
        response = self.client.get(reverse('students:skill_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rendered Skill')
        self.assertContains(response, 'Skills Management')

    def test_student_skill_list_page_renders(self):
        skill = self._create_skill(name='Rendered Skill')
        StudentSkill.objects.create(
            student=self.student, skill=skill, proficiency_level=7
        )
        response = self.client.get(reverse('students:student_skill_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Student Skills')
        self.assertContains(response, 'Doe, Jane')
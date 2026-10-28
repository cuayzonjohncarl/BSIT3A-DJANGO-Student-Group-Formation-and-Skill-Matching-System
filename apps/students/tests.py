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
    YEAR_LEVEL_CHOICES,
)
from .views import _parse_proficiency, _parse_year_level


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

    def test_student_year_level_field(self):
        field = Student._meta.get_field('year_level')
        self.assertEqual(field.get_internal_type(), 'PositiveSmallIntegerField')
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertEqual(
            dict(field.choices),
            {1: '1st Year', 2: '2nd Year', 3: '3rd Year', 4: '4th Year'},
        )
        self.assertEqual(dict(YEAR_LEVEL_CHOICES), dict(field.choices))


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
            year_level=2,
        )

    def test_simple_str_methods(self):
        skill = Skill(skill_id=1, skill_name='Python')
        project = Project(project_id=1, project_name='Website')
        group = Group(group_id=1, group_name='Alpha')
        self.assertEqual(str(skill), 'Python')
        self.assertEqual(str(project), 'Website')
        self.assertEqual(str(group), 'Alpha')

    def test_year_level_display(self):
        self.assertEqual(self._student().get_year_level_display(), '2nd Year')
        self.assertEqual(
            Student(year_level=None).get_year_level_display(), None
        )

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


class StudentYearLevelParsingTests(SimpleTestCase):
    """The year level parser accepts integers 1-4 and is optional (blank -> None)."""

    def test_valid_values(self):
        for raw, expected in [('1', 1), ('2', 2), ('3', 3), ('4', 4), (' 3 ', 3)]:
            with self.subTest(raw=raw):
                self.assertEqual(_parse_year_level(raw), expected)

    def test_blank_values_return_none(self):
        for raw in ['', '   ', None]:
            with self.subTest(raw=raw):
                self.assertIsNone(_parse_year_level(raw))

    def test_out_of_range_and_non_numeric_return_none(self):
        for raw in ['0', '5', '-1', 'abc', '2.5', '1e3', '10']:
            with self.subTest(raw=raw):
                self.assertIsNone(_parse_year_level(raw))


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

    def test_assignment_accepts_proficiency_boundaries(self):
        low_skill = self._create_skill(name='Python')
        high_skill = self._create_skill(name='Java')

        low = self._save_assignment(
            student_id=str(self.student.pk), skill_id=str(low_skill.pk),
            proficiency_level='1',
        )
        high = self._save_assignment(
            student_id=str(self.student.pk), skill_id=str(high_skill.pk),
            proficiency_level='5',
        )

        self.assertEqual(low.status_code, 200)
        self.assertEqual(high.status_code, 200)
        self.assertEqual(
            StudentSkill.objects.get(skill=low_skill).proficiency_level, 1
        )
        self.assertEqual(
            StudentSkill.objects.get(skill=high_skill).proficiency_level, 5
        )

    def test_assignment_rejects_out_of_range_proficiency(self):
        skill = self._create_skill()
        for raw in ['0', '6', '-100']:
            with self.subTest(proficiency_level=raw):
                response = self._save_assignment(
                    student_id=str(self.student.pk), skill_id=str(skill.pk),
                    proficiency_level=raw,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())
        self.assertEqual(StudentSkill.objects.count(), 0)

    def test_assignment_rejects_fractional_proficiency(self):
        skill = self._create_skill()
        response = self._save_assignment(
            student_id=str(self.student.pk), skill_id=str(skill.pk),
            proficiency_level='2.5',
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

    def test_student_skill_form_limits_proficiency_to_one_through_five(self):
        response = self.client.get(reverse('students:student_skill_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'min="1" max="5" name="proficiency_level"')


class Stage3UrlResolutionTests(SimpleTestCase):
    """Verify the Stage 3 project and project-skill routes are wired up."""

    EXPECTED = {
        '/students/projects/': 'students:project_list',
        '/students/projects/ajax/list/': 'students:project_list_ajax',
        '/students/projects/ajax/get/1/': 'students:project_get_ajax',
        '/students/projects/ajax/save/': 'students:project_save_ajax',
        '/students/projects/ajax/delete/1/': 'students:project_delete_ajax',
        '/students/project-skills/': 'students:project_skill_list',
        '/students/project-skills/ajax/list/': 'students:project_skill_list_ajax',
        '/students/project-skills/ajax/get/1/': 'students:project_skill_get_ajax',
        '/students/project-skills/ajax/save/': 'students:project_skill_save_ajax',
        '/students/project-skills/ajax/delete/1/': 'students:project_skill_delete_ajax',
    }

    def test_paths_resolve_to_expected_view_names(self):
        for path, view_name in self.EXPECTED.items():
            with self.subTest(path=path):
                self.assertEqual(resolve(path).view_name, view_name)

    def test_named_urls_reverse(self):
        self.assertEqual(reverse('students:project_list'), '/students/projects/')
        self.assertEqual(
            reverse('students:project_save_ajax'), '/students/projects/ajax/save/'
        )
        self.assertEqual(
            reverse('students:project_skill_list'), '/students/project-skills/'
        )
        self.assertEqual(
            reverse('students:project_skill_save_ajax'),
            '/students/project-skills/ajax/save/',
        )


class Stage3LoginRequiredTests(TestCase):
    """Every Stage 3 endpoint must require authentication."""

    def test_anonymous_get_redirects_to_login(self):
        for url in [
            reverse('students:project_list'),
            reverse('students:project_skill_list'),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('next=', response['Location'])

    def test_anonymous_post_redirects_to_login(self):
        for url in [
            reverse('students:project_save_ajax'),
            reverse('students:project_delete_ajax', args=[1]),
            reverse('students:project_skill_save_ajax'),
            reverse('students:project_skill_delete_ajax', args=[1]),
        ]:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn('next=', response['Location'])


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed Stage 3 tests run only with mysite.test_settings (SQLite).',
)
class Stage3ProjectCrudTests(UnmanagedTablesMixin, TransactionTestCase):
    """Exercise the Stage 3 project create/read/update/delete flows on SQLite."""

    def setUp(self):
        ProjectRequiredSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        StudentSkill.objects.all().delete()
        Skill.objects.all().delete()
        Student.objects.all().delete()

        self.user = User.objects.create_user(username='tester', password='secret123')
        self.client.force_login(self.user)

    def _save_project(self, **data):
        return self.client.post(reverse('students:project_save_ajax'), data)

    def test_create_project(self):
        response = self._save_project(project_name='Capstone', description='Final year')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(Project.objects.filter(project_name='Capstone').exists())

    def test_create_project_requires_name(self):
        response = self._save_project(project_name='   ', description='x')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertEqual(Project.objects.count(), 0)

    def test_duplicate_project_name_is_rejected_case_insensitively(self):
        Project.objects.create(project_name='Capstone')
        response = self._save_project(project_name='capstone')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Project.objects.filter(project_name__iexact='capstone').count(), 1)

    def test_edit_project(self):
        project = Project.objects.create(project_name='Capstone')
        response = self._save_project(
            project_id=str(project.pk), project_name='Capstone II', description='updated'
        )
        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.project_name, 'Capstone II')
        self.assertEqual(project.description, 'updated')

    def test_edit_project_keeps_same_name(self):
        project = Project.objects.create(project_name='Capstone')
        response = self._save_project(project_id=str(project.pk), project_name='Capstone')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Project.objects.count(), 1)

    def test_delete_project(self):
        project = Project.objects.create(project_name='Capstone')
        response = self.client.post(
            reverse('students:project_delete_ajax', args=[project.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_project_list_and_get_endpoints(self):
        project = Project.objects.create(project_name='Capstone')
        list_response = self.client.get(reverse('students:project_list_ajax'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()['total'], 1)

        search_response = self.client.get(
            reverse('students:project_list_ajax'), {'q': 'caps'}
        )
        self.assertEqual(search_response.json()['total'], 1)

        get_response = self.client.get(
            reverse('students:project_get_ajax', args=[project.pk])
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()['project_name'], 'Capstone')

    def test_project_list_page_renders(self):
        Project.objects.create(project_name='Rendered Project')
        response = self.client.get(reverse('students:project_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rendered Project')
        self.assertContains(response, 'Projects Management')


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed Stage 3 tests run only with mysite.test_settings (SQLite).',
)
class Stage3ProjectSkillCrudTests(UnmanagedTablesMixin, TransactionTestCase):
    """Exercise the Stage 3 project-required-skill CRUD flows on SQLite."""

    def setUp(self):
        ProjectRequiredSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        StudentSkill.objects.all().delete()
        Skill.objects.all().delete()
        Student.objects.all().delete()

        self.user = User.objects.create_user(username='tester', password='secret123')
        self.client.force_login(self.user)
        self.project = Project.objects.create(project_name='Capstone')
        self.skill = Skill.objects.create(skill_name='Python')

    def _save_requirement(self, **data):
        return self.client.post(reverse('students:project_skill_save_ajax'), data)

    def test_assign_required_skill_to_project(self):
        response = self._save_requirement(
            project_id=str(self.project.pk), skill_id=str(self.skill.pk),
            required_level='3',
        )
        self.assertEqual(response.status_code, 200)
        requirement = ProjectRequiredSkill.objects.get()
        self.assertEqual(requirement.project_id, self.project.pk)
        self.assertEqual(requirement.skill_id, self.skill.pk)
        self.assertEqual(requirement.required_level, 3)

    def test_requirement_requires_project_and_skill(self):
        missing_project = self._save_requirement(
            skill_id=str(self.skill.pk), required_level='3'
        )
        missing_skill = self._save_requirement(
            project_id=str(self.project.pk), required_level='3'
        )
        self.assertEqual(missing_project.status_code, 400)
        self.assertEqual(missing_skill.status_code, 400)
        self.assertEqual(ProjectRequiredSkill.objects.count(), 0)

    def test_requirement_requires_integer_level(self):
        response = self._save_requirement(
            project_id=str(self.project.pk), skill_id=str(self.skill.pk),
            required_level='expert',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectRequiredSkill.objects.count(), 0)

    def test_requirement_accepts_level_boundaries(self):
        second_skill = Skill.objects.create(skill_name='Django')

        low = self._save_requirement(
            project_id=str(self.project.pk), skill_id=str(self.skill.pk),
            required_level='1',
        )
        high = self._save_requirement(
            project_id=str(self.project.pk), skill_id=str(second_skill.pk),
            required_level='5',
        )

        self.assertEqual(low.status_code, 200)
        self.assertEqual(high.status_code, 200)
        self.assertEqual(
            ProjectRequiredSkill.objects.get(skill=self.skill).required_level, 1
        )
        self.assertEqual(
            ProjectRequiredSkill.objects.get(skill=second_skill).required_level, 5
        )

    def test_requirement_rejects_out_of_range_level(self):
        for raw in ['0', '6', '-76']:
            with self.subTest(required_level=raw):
                response = self._save_requirement(
                    project_id=str(self.project.pk), skill_id=str(self.skill.pk),
                    required_level=raw,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())
        self.assertEqual(ProjectRequiredSkill.objects.count(), 0)

    def test_requirement_rejects_fractional_level(self):
        response = self._save_requirement(
            project_id=str(self.project.pk), skill_id=str(self.skill.pk),
            required_level='2.5',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectRequiredSkill.objects.count(), 0)

    def test_requirement_rejects_non_numeric_ids(self):
        response = self._save_requirement(
            project_id='abc', skill_id='xyz', required_level='3'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertEqual(ProjectRequiredSkill.objects.count(), 0)

    def test_duplicate_requirement_is_rejected(self):
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill, required_level=2
        )
        response = self._save_requirement(
            project_id=str(self.project.pk), skill_id=str(self.skill.pk),
            required_level='5',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectRequiredSkill.objects.count(), 1)

    def test_edit_requirement_level(self):
        requirement = ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill, required_level=2
        )
        response = self._save_requirement(
            project_skill_id=str(requirement.pk),
            project_id=str(self.project.pk),
            skill_id=str(self.skill.pk),
            required_level='5',
        )
        self.assertEqual(response.status_code, 200)
        requirement.refresh_from_db()
        self.assertEqual(requirement.required_level, 5)

    def test_delete_requirement(self):
        requirement = ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill, required_level=2
        )
        response = self.client.post(
            reverse('students:project_skill_delete_ajax', args=[requirement.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProjectRequiredSkill.objects.count(), 0)

    def test_delete_project_with_required_skills_is_blocked(self):
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill, required_level=2
        )
        response = self.client.post(
            reverse('students:project_delete_ajax', args=[self.project.pk])
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_requirement_list_and_get_endpoints(self):
        requirement = ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill, required_level=2
        )
        list_response = self.client.get(reverse('students:project_skill_list_ajax'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()['total'], 1)

        search_response = self.client.get(
            reverse('students:project_skill_list_ajax'), {'q': 'python'}
        )
        self.assertEqual(search_response.json()['total'], 1)

        get_response = self.client.get(
            reverse('students:project_skill_get_ajax', args=[requirement.pk])
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()['skill_name'], 'Python')

    def test_project_skill_list_page_renders(self):
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill, required_level=4
        )
        response = self.client.get(reverse('students:project_skill_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project Required Skills')
        self.assertContains(response, 'Capstone')

    def test_project_skill_form_limits_required_level_to_one_through_five(self):
        response = self.client.get(reverse('students:project_skill_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'min="1" max="5" name="required_level"')


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed student tests run only with mysite.test_settings (SQLite).',
)
class StudentYearLevelCrudTests(UnmanagedTablesMixin, TransactionTestCase):
    """Exercise the optional Year Level (1-4) behaviour of student records."""

    def setUp(self):
        StudentSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        ProjectRequiredSkill.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        Skill.objects.all().delete()
        Student.objects.all().delete()

        self.user = User.objects.create_user(username='tester', password='secret123')
        self.client.force_login(self.user)

    def _save_student(self, **overrides):
        data = {
            'student_number': 'STU-0001',
            'first_name': 'Jane',
            'last_name': 'Doe',
            'email': 'jane@example.com',
            'course': 'BSIT',
            'section': '3A',
        }
        data.update(overrides)
        return self.client.post(reverse('students:student_save_ajax'), data)

    def test_create_student_with_year_level(self):
        response = self._save_student(year_level='2')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['year_level'], 2)
        self.assertEqual(response.json()['year_level_display'], '2nd Year')
        self.assertEqual(Student.objects.get().year_level, 2)

    def test_create_student_without_year_level_is_allowed(self):
        response = self._save_student()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['year_level'])
        self.assertIsNone(Student.objects.get().year_level)

    def test_create_student_with_blank_year_level_is_allowed(self):
        response = self._save_student(year_level='')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Student.objects.get().year_level)

    def test_create_student_rejects_out_of_range_year_level(self):
        for raw in ['0', '5', '-1', '10']:
            with self.subTest(year_level=raw):
                response = self._save_student(
                    student_number='STU-{}'.format(raw.replace('-', 'n')),
                    year_level=raw,
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())
        self.assertEqual(Student.objects.count(), 0)

    def test_create_student_rejects_non_numeric_year_level(self):
        for raw in ['abc', '2.5', '1e3']:
            with self.subTest(year_level=raw):
                response = self._save_student(year_level=raw)
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())
        self.assertEqual(Student.objects.count(), 0)

    def test_edit_student_year_level(self):
        student = Student.objects.create(
            student_number='STU-0001',
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            course='BSIT',
            section='3A',
            year_level=1,
        )
        response = self._save_student(
            student_id=str(student.pk), year_level='4'
        )
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.year_level, 4)

    def test_edit_student_can_clear_year_level(self):
        student = Student.objects.create(
            student_number='STU-0001',
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            course='BSIT',
            section='3A',
            year_level=3,
        )
        response = self._save_student(student_id=str(student.pk), year_level='')
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertIsNone(student.year_level)

    def test_edit_student_without_year_level_key_preserves_none(self):
        student = Student.objects.create(
            student_number='STU-0001',
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            course='BSIT',
            section='3A',
        )
        response = self._save_student(student_id=str(student.pk))
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertIsNone(student.year_level)

    def test_student_list_and_get_include_year_level(self):
        student = Student.objects.create(
            student_number='STU-0001',
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            course='BSIT',
            section='3A',
            year_level=3,
        )
        list_response = self.client.get(reverse('students:student_list_ajax'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()['data'][0]['year_level'], 3)
        self.assertEqual(
            list_response.json()['data'][0]['year_level_display'], '3rd Year'
        )

        get_response = self.client.get(
            reverse('students:student_get_ajax', args=[student.pk])
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()['year_level'], 3)

    def test_student_search_by_year_level(self):
        Student.objects.create(
            student_number='STU-A', first_name='Ann', last_name='Abad',
            email='ann@example.com', course='BSIT', section='A', year_level=1,
        )
        Student.objects.create(
            student_number='STU-B', first_name='Ben', last_name='Basa',
            email='ben@example.com', course='BSIT', section='B', year_level=2,
        )

        first_year = self.client.get(
            reverse('students:student_list_ajax'), {'q': '1'}
        )
        self.assertEqual(first_year.json()['total'], 1)
        self.assertEqual(first_year.json()['data'][0]['year_level'], 1)

        second_year = self.client.get(
            reverse('students:student_list_ajax'), {'q': '2'}
        )
        self.assertEqual(second_year.json()['total'], 1)
        self.assertEqual(second_year.json()['data'][0]['year_level'], 2)

    def test_student_form_has_optional_year_level_select(self):
        response = self.client.get(reverse('students:student_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="year_level"')
        for label in ['1st Year', '2nd Year', '3rd Year', '4th Year']:
            with self.subTest(label=label):
                self.assertContains(response, label)


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed Stage 4 tests run only with mysite.test_settings (SQLite).',
)
class Stage4GroupAndMatchingTests(UnmanagedTablesMixin, TransactionTestCase):
    """Exercise Group Formation, Member Roster, and Skill Matching/Gap Analysis."""

    def setUp(self):
        super().setUp()
        # Clear unmanaged tables for isolation
        GroupMember.objects.all().delete()
        ProjectRequiredSkill.objects.all().delete()
        StudentSkill.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        Skill.objects.all().delete()
        Student.objects.all().delete()

        self.user = User.objects.create_user(username='tester4', password='password123')
        self.client.force_login(self.user)

        self.project = Project.objects.create(
            project_name='Barangay Information System',
            description='Digitize resident records and services.'
        )
        self.skill_backend = Skill.objects.create(
            skill_name='Backend Web Development',
            description='Python/Django server development.'
        )
        self.skill_db = Skill.objects.create(
            skill_name='Database Design & Management',
            description='Relational schema design and queries.'
        )

        # Set Project Requirements
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill_backend, required_level=3
        )
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.skill_db, required_level=3
        )

        # Create Students
        self.student1 = Student.objects.create(
            student_number='2024-001', first_name='John Carl', last_name='Cuayzon',
            email='johncarl@example.com', course='BSIT', section='3A', year_level=3
        )
        self.student2 = Student.objects.create(
            student_number='2024-002', first_name='Ryan', last_name='Balinas',
            email='ryan@example.com', course='BSIT', section='3A', year_level=3
        )

        # Assign Skills
        StudentSkill.objects.create(
            student=self.student1, skill=self.skill_backend, proficiency_level=4
        )
        StudentSkill.objects.create(
            student=self.student2, skill=self.skill_db, proficiency_level=2
        )


    def test_group_create_and_duplicate_prevention(self):
        # Create group
        resp = self.client.post(reverse('students:group_save_ajax'), {
            'project_id': self.project.project_id,
            'group_name': 'Team Alpha',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'success')
        self.assertTrue(Group.objects.filter(group_name='Team Alpha').exists())

        # Attempt duplicate name under same project
        dup_resp = self.client.post(reverse('students:group_save_ajax'), {
            'project_id': self.project.project_id,
            'group_name': 'Team Alpha',
        })
        self.assertEqual(dup_resp.status_code, 400)
        self.assertIn('already exists', dup_resp.json()['error'])

    def test_member_assignment_and_skill_gap_analysis(self):
        group = Group.objects.create(project=self.project, group_name='CyberSquad')

        # Add Student 1 (has Backend Level 4 vs req 3)
        add_resp = self.client.post(
            reverse('students:group_member_add_ajax', kwargs={'group_pk': group.group_id}),
            {'student_id': self.student1.student_id}
        )
        self.assertEqual(add_resp.status_code, 200)
        analysis = add_resp.json()['analysis']

        # 1 of 2 required skills satisfied -> 50% match
        self.assertEqual(analysis['match_percentage'], 50)
        self.assertEqual(analysis['satisfied_count'], 1)
        self.assertEqual(analysis['missing_count'], 1)

        # Add Student 2 (has Database Level 2 vs req 3)
        add2_resp = self.client.post(
            reverse('students:group_member_add_ajax', kwargs={'group_pk': group.group_id}),
            {'student_id': self.student2.student_id}
        )
        self.assertEqual(add2_resp.status_code, 200)
        analysis2 = add2_resp.json()['analysis']

        # Still 50% because Student 2 is deficient (level 2 < req 3)
        self.assertEqual(analysis2['match_percentage'], 50)
        self.assertEqual(analysis2['deficient_count'], 1)

        # Upgrade Student 2 proficiency to 3
        ss = StudentSkill.objects.get(student=self.student2, skill=self.skill_db)
        ss.proficiency_level = 3
        ss.save()

        # Re-fetch analysis
        get_resp = self.client.get(reverse('students:group_get_ajax', kwargs={'pk': group.group_id}))
        final_analysis = get_resp.json()['analysis']
        self.assertEqual(final_analysis['match_percentage'], 100)
        self.assertEqual(final_analysis['gap_count'], 0)

    def test_prevent_student_in_multiple_groups_for_same_project(self):
        group_a = Group.objects.create(project=self.project, group_name='Team A')
        group_b = Group.objects.create(project=self.project, group_name='Team B')

        # Add student1 to Group A
        self.client.post(
            reverse('students:group_member_add_ajax', kwargs={'group_pk': group_a.group_id}),
            {'student_id': self.student1.student_id}
        )

        # Attempt to add student1 to Group B (same project)
        conflict_resp = self.client.post(
            reverse('students:group_member_add_ajax', kwargs={'group_pk': group_b.group_id}),
            {'student_id': self.student1.student_id}
        )
        self.assertEqual(conflict_resp.status_code, 400)
        self.assertIn('already a member', conflict_resp.json()['error'])

    def test_group_recommendations_exclude_assigned_and_score_by_coverage(self):
        group = Group.objects.create(project=self.project, group_name='Team Rec')
        # student1 has backend level 4 (meets req 3), student2 has db level 2 (< req 3)
        resp = self.client.get(reverse('students:group_recommendations_ajax', kwargs={'group_pk': group.group_id}))
        self.assertEqual(resp.status_code, 200)
        recs = resp.json()['recommendations']
        self.assertEqual(len(recs), 2)
        # student1 should rank higher (covers backend)
        self.assertEqual(recs[0]['student_id'], self.student1.student_id)
        self.assertTrue(recs[0]['coverage_pct'] >= 50)
        self.assertTrue(any(m['skill_name'] == 'Backend Web Development' for m in recs[0]['met']))

        # Assign student1 to another group in same project - should be excluded
        group2 = Group.objects.create(project=self.project, group_name='Team Other')
        self.client.post(reverse('students:group_member_add_ajax', kwargs={'group_pk': group2.group_id}),
                         {'student_id': self.student1.student_id})
        resp2 = self.client.get(reverse('students:group_recommendations_ajax', kwargs={'group_pk': group.group_id}))
        recs2 = resp2.json()['recommendations']
        self.assertEqual(len(recs2), 1)
        self.assertEqual(recs2[0]['student_id'], self.student2.student_id)

    def test_group_recommendations_edge_cases(self):
        # Project with no requirements
        project_empty = Project.objects.create(project_name='Empty Project')
        group_empty = Group.objects.create(project=project_empty, group_name='EmptyTeam')
        resp = self.client.get(reverse('students:group_recommendations_ajax', kwargs={'group_pk': group_empty.group_id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['recommendations'], [])

        # Project with requirement but student has no skills
        project3 = Project.objects.create(project_name='Proj3')
        skill_x = Skill.objects.create(skill_name='Testing', description='QA')
        ProjectRequiredSkill.objects.create(project=project3, skill=skill_x, required_level=4)
        student3 = Student.objects.create(
            student_number='2024-003', first_name='Alex', last_name='Cruz',
            email='alex@example.com', course='BSIT', section='3A', year_level=3
        )
        group3 = Group.objects.create(project=project3, group_name='Team3')
        resp3 = self.client.get(reverse('students:group_recommendations_ajax', kwargs={'group_pk': group3.group_id}))
        self.assertEqual(resp3.status_code, 200)
        recs3 = resp3.json()['recommendations']
        self.assertTrue(len(recs3) >= 1)
        # Find our student
        rec_s3 = [r for r in recs3 if r['student_id'] == student3.student_id][0]
        self.assertEqual(rec_s3['coverage_pct'], 0)
        self.assertEqual(len(rec_s3['missing']), 1)
        self.assertEqual(rec_s3['missing'][0]['have'], 0)


    def test_group_recommendations_requires_login(self):
        group = Group.objects.create(project=self.project, group_name='TeamAnon')
        self.client.logout()
        resp = self.client.get(reverse('students:group_recommendations_ajax', kwargs={'group_pk': group.group_id}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue('login' in resp['Location'].lower() or 'next=' in resp['Location'].lower())

from unittest import skipUnless

from django.contrib.auth.models import User
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import resolve, reverse

from .group_formation import MAX_GROUP_MEMBERS, group_label, plan_groups, save_plan
from .matching import (
    analyze_group_skills,
    match_student_to_requirements,
    match_students_to_project,
    proficiency_label,
    proficiency_scale_text,
    recommend_candidates,
)
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

    def test_skill_list_page_renders_expandable_descriptions(self):
        self._create_skill(
            name='Rendered Skill',
            description='First line of description.\nSecond line of description.',
        )
        self._create_skill(name='Undescribed Skill', description=None)

        response = self.client.get(reverse('students:skill_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rendered Skill')
        self.assertContains(response, 'Skills Management')
        self.assertContains(response, 'data-bs-toggle="collapse"')
        self.assertContains(response, 'aria-controls="skillDescription')
        self.assertContains(response, 'First line of description.')
        self.assertContains(response, 'Second line of description.')
        self.assertContains(response, 'No description provided.')
        self.assertContains(response, 'data-mode="edit"')
        self.assertNotContains(response, 'viewSkillDescriptionModal')

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

    def test_prevent_student_in_multiple_groups_across_projects(self):
        other_project = Project.objects.create(project_name='Other Capstone')
        group_a = Group.objects.create(project=self.project, group_name='Team A')
        group_b = Group.objects.create(project=other_project, group_name='Team B')

        added = self.client.post(
            reverse(
                'students:group_member_add_ajax',
                kwargs={'group_pk': group_a.group_id},
            ),
            {'student_id': self.student1.student_id},
        )
        self.assertEqual(added.status_code, 200)

        conflict_resp = self.client.post(
            reverse(
                'students:group_member_add_ajax',
                kwargs={'group_pk': group_b.group_id},
            ),
            {'student_id': self.student1.student_id},
        )
        self.assertEqual(conflict_resp.status_code, 400)
        self.assertIn('already a member', conflict_resp.json()['error'])
        self.assertIn(self.project.project_name, conflict_resp.json()['error'])
        self.assertEqual(
            GroupMember.objects.filter(student=self.student1).count(), 1
        )

    def test_unassigned_students_excludes_global_members(self):
        group = Group.objects.create(project=self.project, group_name='Team A')
        other_project = Project.objects.create(project_name='Other Capstone')
        other_group = Group.objects.create(
            project=other_project, group_name='Other Team'
        )
        unassigned = Student.objects.create(
            student_number='2024-003',
            first_name='Alex',
            last_name='Cruz',
            email='alex@example.com',
            course='BSIT',
            section='3A',
            year_level=3,
        )
        GroupMember.objects.create(group=group, student=self.student1)
        GroupMember.objects.create(group=other_group, student=self.student2)

        response = self.client.get(
            reverse(
                'students:group_unassigned_students_ajax',
                kwargs={'group_pk': group.group_id},
            )
        )

        self.assertEqual(response.status_code, 200)
        available_ids = {
            student['student_id'] for student in response.json()['students']
        }
        self.assertNotIn(self.student1.student_id, available_ids)
        self.assertNotIn(self.student2.student_id, available_ids)
        self.assertEqual(available_ids, {unassigned.student_id})

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

    def test_group_recommendations_exclude_students_assigned_elsewhere(self):
        group = Group.objects.create(project=self.project, group_name='Team Rec')
        other_project = Project.objects.create(project_name='Other Capstone')
        other_group = Group.objects.create(
            project=other_project, group_name='Other Team'
        )
        GroupMember.objects.create(group=other_group, student=self.student1)

        resp = self.client.get(
            reverse(
                'students:group_recommendations_ajax',
                kwargs={'group_pk': group.group_id},
            )
        )

        self.assertEqual(resp.status_code, 200)
        rec_ids = {
            rec['student_id'] for rec in resp.json()['recommendations']
        }
        self.assertNotIn(self.student1.student_id, rec_ids)
        self.assertIn(self.student2.student_id, rec_ids)

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


class IndividualVsGroupCoverageTests(UnmanagedTablesMixin, TransactionTestCase):
    """A student's compatibility index and a group's combined coverage agree.

    The individual index is a weighted mean of ``min(level / required, 1)``
    per requirement. The group uses the **best** proficiency any member has
    for each requirement, so the combined coverage can never be lower than the
    best member's individual index, and it hits 100% exactly when every
    requirement is covered at the required level by at least one member.
    """

    def setUp(self):
        self.project = Project.objects.create(project_name='Combined Coverage Project')
        self.backend = Skill.objects.create(skill_name='Backend Web Development', description='API')
        self.frontend = Skill.objects.create(skill_name='Frontend Development', description='UI')
        ProjectRequiredSkill.objects.create(project=self.project, skill=self.backend, required_level=4)
        ProjectRequiredSkill.objects.create(project=self.project, skill=self.frontend, required_level=2)

        # Ana covers backend fully, Bea covers design fully: together they
        # close every requirement, individually neither of them does.
        self.ana = Student.objects.create(
            student_number='2024-901', first_name='Ana', last_name='Santos',
            email='ana@example.com', course='BSIT', section='3A', year_level=3,
        )
        self.bea = Student.objects.create(
            student_number='2024-902', first_name='Bea', last_name='Cruz',
            email='bea@example.com', course='BSIT', section='3A', year_level=3,
        )
        self.cara = Student.objects.create(
            student_number='2024-903', first_name='Cara', last_name='Diaz',
            email='cara@example.com', course='BSIT', section='3A', year_level=3,
        )

        StudentSkill.objects.create(student=self.ana, skill=self.backend, proficiency_level=4)
        StudentSkill.objects.create(student=self.cara, skill=self.frontend, proficiency_level=2)
        # Bea is recorded twice for the same skill - the engines must collapse
        # duplicates to the highest level (2), not double count them.
        StudentSkill.objects.create(student=self.bea, skill=self.backend, proficiency_level=1)
        StudentSkill.objects.create(student=self.bea, skill=self.backend, proficiency_level=2)

        self.group = Group.objects.create(project=self.project, group_name='Alpha Team')
        GroupMember.objects.create(group=self.group, student=self.ana)
        GroupMember.objects.create(group=self.group, student=self.bea)

        self.results = {r['student_id']: r for r in match_students_to_project(self.project)}
        self.analysis = analyze_group_skills(self.group)

    def test_individual_scores_are_reproducible(self):
        # Weighted total = 4 (Backend) + 2 (Frontend) = 6.
        # Ana: Backend met (4/4 -> 4 pts), Frontend missing -> 4/6 = 67%.
        self.assertEqual(self.results[self.ana.student_id]['score'], 67)
        # Bea: the duplicate Backend rows collapse to the higher level (2/4
        # -> 2 pts) and Frontend is not recorded -> 2/6 = 33%.
        self.assertEqual(self.results[self.bea.student_id]['score'], 33)
        # Cara is not in the group but must still be scored consistently:
        # Frontend met (2/2 -> 2 pts), Backend missing -> 2/6 = 33%.
        self.assertEqual(self.results[self.cara.student_id]['score'], 33)

        # Recomputing must return identical scores.
        repeat = {r['student_id']: r for r in match_students_to_project(self.project)}
        for student_id, original in self.results.items():
            self.assertEqual(repeat[student_id]['score'], original['score'])

    def test_combined_coverage_is_never_below_the_best_member(self):
        best_member = max(self.results[s.student_id]['score']
                          for s in self.group.members.select_related('student'))
        # Group = Ana + Bea: best Backend level is 4 (Ana, full credit 4/4);
        # nobody recorded Frontend (0/2). weighted = 4/6 = 67%, which equals
        # the best member's own index and can never fall below it.
        self.assertEqual(best_member, 67)
        self.assertEqual(self.analysis['weighted_pct'], 67)
        self.assertGreaterEqual(self.analysis['weighted_pct'], best_member)
        # 1 of the 2 requirements is satisfied.
        self.assertEqual(self.analysis['match_percentage'], 50)

    def test_combination_adds_value_beyond_individual_scores(self):
        # Ana + Bea only reach 67% because Frontend is uncovered. Adding Cara
        # (Frontend 2) closes the remaining requirement, so the combined
        # coverage ends up higher than any single member's own index.
        best_individual = max(
            r['score'] for r in self.results.values()
        )
        GroupMember.objects.create(group=self.group, student=self.cara)
        analysis = analyze_group_skills(self.group)

        self.assertLess(self.results[self.bea.student_id]['score'], analysis['weighted_pct'])
        self.assertGreater(analysis['weighted_pct'], best_individual)
        self.assertEqual(analysis['weighted_pct'], 100)
        self.assertEqual(analysis['satisfied_count'], 2)
        self.assertEqual(analysis['deficient_count'], 0)
        self.assertEqual(analysis['missing_count'], 0)

    def test_weaker_members_do_not_drag_combined_coverage_down(self):
        # Cara joins with Frontend 2 (exactly the required level), lifting the
        # group from 67% to 100%. The best-level rule means extra members can
        # only raise coverage, never lower it.
        GroupMember.objects.create(group=self.group, student=self.cara)
        analysis = analyze_group_skills(self.group)
        self.assertEqual(analysis['weighted_pct'], 100)
        self.assertEqual(analysis['match_percentage'], 100)
        self.assertGreaterEqual(analysis['weighted_pct'], self.analysis['weighted_pct'])

        # A student with no recorded skills must not move the numbers at all.
        nobody = Student.objects.create(
            student_number='2024-904', first_name='Dan', last_name='Reyes',
            email='dan@example.com', course='BSIT', section='3A', year_level=3,
        )
        GroupMember.objects.create(group=self.group, student=nobody)
        after = analyze_group_skills(self.group)
        self.assertEqual(after['weighted_pct'], analysis['weighted_pct'])
        self.assertEqual(after['match_percentage'], analysis['match_percentage'])

    def test_empty_group_scores_zero_against_requirements(self):
        empty = Group.objects.create(project=self.project, group_name='Empty Team')
        analysis = analyze_group_skills(empty)
        self.assertEqual(analysis['weighted_pct'], 0)
        self.assertEqual(analysis['match_percentage'], 0)
        self.assertEqual(analysis['missing_count'], 2)

    def test_matching_page_renders_breakdown_toggle(self):
        """The 'Why NN%' control expands into a full-width breakdown row."""
        # The matching page is behind login like every other app page.
        user = User.objects.create_user(username='whyviewer', password='secret1234')
        self.client.force_login(user)

        response = self.client.get(reverse('students:matching'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'students/matching.html')
        content = response.content.decode()
        self.assertIn('sg-why-btn', content)
        self.assertIn('aria-controls="why-1"', content)
        self.assertIn('sg-why-row', content)
        # Every breakdown row must be able to span the whole table.
        self.assertIn('colspan="6"', content)


# ---------------------------------------------------------------------------
# Stage 7 - matching engine, automated group formation, role enforcement
# ---------------------------------------------------------------------------

class Stage7UrlResolutionTests(SimpleTestCase):
    """The new matching and formation endpoints must reverse correctly."""

    def test_paths_resolve_to_expected_view_names(self):
        cases = {
            '/students/matching/': 'matching',
            '/students/groups/ajax/automate/': 'group_automate_ajax',
            '/students/groups/ajax/automate/save/': 'group_automate_save_ajax',
        }
        for url, name in cases.items():
            with self.subTest(url=url):
                self.assertEqual(resolve(url).url_name, name)

    def test_named_urls_reverse(self):
        self.assertEqual(reverse('students:matching'), '/students/matching/')
        self.assertEqual(
            reverse('students:group_automate_ajax'),
            '/students/groups/ajax/automate/',
        )
        self.assertEqual(
            reverse('students:group_automate_save_ajax'),
            '/students/groups/ajax/automate/save/',
        )


class Stage7MatchingEngineTests(SimpleTestCase):
    """Objective 3: the compatibility index must be explainable and exact.

    These functions are pure, so they are tested without touching a database.
    """

    class StubStudent:
        def __init__(self, **kwargs):
            self.student_id = kwargs.get('student_id', 1)
            self.student_number = kwargs.get('student_number', '2026-0001')
            self.first_name = kwargs.get('first_name', 'Jane')
            self.last_name = kwargs.get('last_name', 'Doe')
            self.course = kwargs.get('course', 'BSIT')
            self.section = kwargs.get('section', 'A')
            self.year_level = kwargs.get('year_level', 3)

    REQUIREMENTS = [
        {'skill_id': 1, 'skill_name': 'Backend', 'required_level': 4},
        {'skill_id': 2, 'skill_name': 'Frontend', 'required_level': 1},
    ]

    def test_score_is_weighted_by_required_level(self):
        # Backend 2/4 of a weight-4 requirement (2) + Frontend full (1) = 3/5
        result = match_student_to_requirements(
            self.StubStudent(), {1: 2, 2: 1}, self.REQUIREMENTS
        )
        self.assertEqual(result['score'], 60)
        self.assertEqual(result['met_count'], 1)
        self.assertEqual(result['deficient_count'], 1)
        self.assertEqual(result['missing_count'], 0)

    def test_overqualification_is_capped_at_100(self):
        result = match_student_to_requirements(
            self.StubStudent(), {1: 5, 2: 5}, self.REQUIREMENTS
        )
        self.assertEqual(result['score'], 100)

    def test_unrecorded_skill_counts_as_missing(self):
        result = match_student_to_requirements(self.StubStudent(), {}, self.REQUIREMENTS)
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['missing_count'], 2)
        self.assertIn('missing: Backend', result['explanation'])

    def test_project_without_requirements_scores_100(self):
        result = match_student_to_requirements(self.StubStudent(), {}, [])
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['total'], 0)
        self.assertIn('no required skills', result['explanation'])

    def test_proficiency_scale_labels(self):
        self.assertEqual(proficiency_label(1), 'Beginner')
        self.assertEqual(proficiency_label(2), 'Elementary')
        self.assertEqual(proficiency_label(3), 'Intermediate')
        self.assertEqual(proficiency_label(4), 'Advanced')
        self.assertEqual(proficiency_label(5), 'Expert')
        self.assertIn('2 = Elementary', proficiency_scale_text())

    def test_identical_input_produces_identical_output(self):
        first = match_student_to_requirements(
            self.StubStudent(), {1: 3}, self.REQUIREMENTS
        )
        second = match_student_to_requirements(
            self.StubStudent(), {1: 3}, self.REQUIREMENTS
        )
        self.assertEqual(first, second)


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed Stage 7 tests run only with mysite.test_settings (SQLite).',
)
class Stage7GroupFormationTests(UnmanagedTablesMixin, TransactionTestCase):
    """Objective 4: automated balanced group formation."""

    def setUp(self):
        StudentSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        ProjectRequiredSkill.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        Skill.objects.all().delete()
        Student.objects.all().delete()

        self.backend = Skill.objects.create(skill_name='Backend')
        self.frontend = Skill.objects.create(skill_name='Frontend')
        self.project = Project.objects.create(project_name='Capstone')
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.backend, required_level=3
        )
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.frontend, required_level=3
        )

        self.students = []

    def _student(self, index, skills=None):
        student = Student.objects.create(
            student_number=f'2026-{index:04d}',
            first_name=f'Student{index}',
            last_name=f'Family{index}',
            email=f'student{index}@example.com',
            course='BSIT',
            section='3A',
            year_level=3,
        )
        self.students.append(student)
        for skill, level in (skills or {}).items():
            StudentSkill.objects.create(
                student=student, skill=skill, proficiency_level=level
            )
        return student

    def _pool(self):
        return list(Student.objects.order_by('student_id'))

    def _login_instructor(self, username):
        from apps.core.roles import ROLE_INSTRUCTOR, set_role

        instructor = User.objects.create_user(
            username=username, password='secret1234'
        )
        set_role(instructor, ROLE_INSTRUCTOR)
        self.client.force_login(instructor)

    def _formation_urls(self):
        return (
            'students:group_automate_ajax',
            'students:group_automate_save_ajax',
        )

    def test_group_count_derived_from_pool_size(self):
        for i in range(6):
            self._student(i + 1, {self.backend: 3, self.frontend: 3})

        plan = plan_groups(self.project, self._pool(), max_members=3)

        self.assertTrue(plan['ok'])
        self.assertEqual(plan['group_count'], 2)
        self.assertEqual([g['size'] for g in plan['groups']], [3, 3])
        self.assertEqual(plan['stats']['assigned_count'], 6)
        self.assertEqual(plan['unassigned'], [])
        self.assertEqual([g['label'] for g in plan['groups']], ['Group A', 'Group B'])

    def test_group_count_derived_from_pool_size_is_capped_at_ten(self):
        for i in range(51):
            self._student(i + 1)

        plan = plan_groups(self.project, self._pool(), max_members=5)

        self.assertTrue(plan['ok'])
        self.assertEqual(plan['group_count'], 10)
        self.assertEqual([group['size'] for group in plan['groups']], [5] * 10)
        self.assertEqual(len(plan['unassigned']), 1)
        self.assertTrue(any('Capacity' in warning for warning in plan['warnings']))

    def test_capacity_is_respected_and_overflow_is_reported(self):
        for i in range(5):
            self._student(i + 1, {self.backend: 3})

        plan = plan_groups(
            self.project, self._pool(), group_count=1, max_members=2
        )

        self.assertTrue(plan['ok'])
        self.assertEqual(plan['group_count'], 1)
        self.assertEqual(plan['groups'][0]['size'], 2)
        self.assertEqual(len(plan['unassigned']), 3)
        self.assertTrue(any('Capacity' in warning for warning in plan['warnings']))

    def test_plan_is_deterministic(self):
        for i in range(6):
            self._student(i + 1, {self.backend: 3 if i % 2 else 1})

        first = plan_groups(self.project, self._pool(), max_members=3)
        second = plan_groups(self.project, self._pool(), max_members=3)

        self.assertEqual(first['groups'], second['groups'])
        self.assertEqual(first['stats'], second['stats'])

    def test_complementary_skills_are_spread_across_groups(self):
        # Three backend specialists and three frontend specialists: a balanced
        # plan must give every group at least one of each.
        for i in range(3):
            self._student(i + 1, {self.backend: 3})
        for i in range(3, 6):
            self._student(i + 1, {self.frontend: 3})

        plan = plan_groups(self.project, self._pool(), max_members=3)

        self.assertEqual(plan['group_count'], 2)
        for group in plan['groups']:
            self.assertEqual(group['size'], 3)
            self.assertEqual(group['coverage'], 100, group['label'])
            self.assertEqual(group['unmet'], [])

    def test_students_without_recorded_skills_are_still_placed(self):
        self._student(1, {self.backend: 3, self.frontend: 3})
        self._student(2)  # no skills at all
        self._student(3)  # no skills at all

        plan = plan_groups(self.project, self._pool(), max_members=2)

        self.assertTrue(plan['ok'])
        self.assertEqual(plan['stats']['assigned_count'], 3)
        self.assertEqual(plan['stats']['students_without_skills'], 2)
        self.assertTrue(any('no recorded skills' in w for w in plan['warnings']))

    def test_empty_pool_is_reported_as_an_error(self):
        plan = plan_groups(self.project, [], max_members=3)

        self.assertFalse(plan['ok'])
        self.assertEqual(plan['group_count'], 0)
        self.assertTrue(plan['errors'])
        self.assertEqual(plan['groups'], [])

    def test_save_plan_persists_groups_and_members_without_duplicates(self):
        for i in range(6):
            self._student(i + 1, {self.backend: 3, self.frontend: 3})

        plan = plan_groups(self.project, self._pool(), max_members=3)
        group_ids = save_plan(self.project, plan)

        self.assertEqual(len(group_ids), 2)
        self.assertEqual(Group.objects.filter(project=self.project).count(), 2)
        self.assertEqual(
            GroupMember.objects.filter(group__project=self.project).count(), 6
        )
        # No student may appear in more than one generated group.
        memberships = GroupMember.objects.filter(
            group__project=self.project
        ).values_list('student_id', flat=True)
        self.assertEqual(len(memberships), len(set(memberships)))
        self.assertEqual(
            list(Group.objects.filter(project=self.project).values_list('group_name', flat=True)),
            ['Group A', 'Group B'],
        )

    def test_save_plan_avoids_duplicate_group_names(self):
        for i in range(2):
            self._student(i + 1, {self.backend: 3})
        Group.objects.create(project=self.project, group_name='Group A')

        plan = plan_groups(self.project, self._pool(), group_count=1, max_members=2)
        save_plan(self.project, plan)

        names = sorted(Group.objects.filter(project=self.project).values_list('group_name', flat=True))
        self.assertEqual(names, ['Group A', 'Group A (2)'])

    def test_save_plan_skips_students_assigned_in_any_project(self):
        assigned = self._student(1, {self.backend: 3})
        available = self._student(2, {self.backend: 3})
        other_project = Project.objects.create(project_name='Other Project')
        existing = Group.objects.create(
            project=other_project, group_name='Existing Group'
        )
        GroupMember.objects.create(group=existing, student=assigned)

        plan = plan_groups(
            self.project,
            [assigned, available],
            group_count=2,
            max_members=2,
        )
        group_ids = save_plan(self.project, plan)

        self.assertEqual(len(group_ids), 1)
        self.assertEqual(
            GroupMember.objects.filter(group=existing, student=assigned).count(),
            1,
        )
        self.assertEqual(
            GroupMember.objects.filter(
                student=assigned, group__project=self.project
            ).count(),
            0,
        )
        self.assertEqual(
            GroupMember.objects.filter(
                group__project=self.project, student=available
            ).count(),
            1,
        )
        self.assertFalse(
            Group.objects.filter(project=self.project, members__isnull=True).exists()
        )

    def test_automated_formation_excludes_students_assigned_elsewhere(self):
        self._login_instructor('formation-existing-member')
        students = [
            self._student(index + 1, {self.backend: 3}) for index in range(4)
        ]
        other_project = Project.objects.create(project_name='Other Project')
        existing = Group.objects.create(
            project=other_project, group_name='Existing Group'
        )
        GroupMember.objects.create(group=existing, student=students[0])
        payload = {'project_id': self.project.project_id, 'max_members': 2}

        preview = self.client.post(
            reverse('students:group_automate_ajax'), payload
        )
        self.assertEqual(preview.status_code, 200)
        preview_ids = [
            member['student_id']
            for group in preview.json()['groups']
            for member in group['members']
        ]
        self.assertNotIn(students[0].student_id, preview_ids)
        self.assertEqual(len(preview_ids), 3)

        response = self.client.post(
            reverse('students:group_automate_save_ajax'), payload
        )

        self.assertEqual(response.status_code, 200)
        memberships = GroupMember.objects.filter(group__project=self.project)
        self.assertEqual(memberships.count(), 3)
        self.assertFalse(memberships.filter(student=students[0]).exists())
        self.assertEqual(
            GroupMember.objects.filter(student=students[0], group=existing).count(),
            1,
        )
        student_ids = list(
            GroupMember.objects.values_list('student_id', flat=True)
        )
        self.assertEqual(len(student_ids), len(set(student_ids)))

    def test_group_label_sequence(self):
        self.assertEqual(group_label(0), 'Group A')
        self.assertEqual(group_label(25), 'Group Z')
        self.assertEqual(group_label(26), 'Group AA')

    def test_gap_analysis_reports_partial_coverage(self):
        student = self._student(1, {self.backend: 2})
        group = Group.objects.create(project=self.project, group_name='Partial')
        GroupMember.objects.create(group=group, student=student)

        analysis = analyze_group_skills(group)

        self.assertEqual(analysis['total_required'], 2)
        self.assertEqual(analysis['satisfied_count'], 0)
        self.assertEqual(analysis['deficient_count'], 1)
        self.assertEqual(analysis['missing_count'], 1)
        self.assertEqual(analysis['match_percentage'], 0)
        # Backend is level 2 of 3 = 2/3 credit, Frontend 0 => 33% weighted.
        self.assertEqual(analysis['weighted_pct'], 33)
        statuses = {d['skill_name']: d['status'] for d in analysis['details']}
        self.assertEqual(statuses['Backend'], 'deficient')
        self.assertEqual(statuses['Frontend'], 'missing')

    def test_recommendations_rank_gap_fillers_first(self):
        weak = self._student(1, {self.backend: 1})
        strong = self._student(2, {self.frontend: 5})
        group = Group.objects.create(project=self.project, group_name='Team')
        GroupMember.objects.create(group=group, student=weak)

        recommendations = recommend_candidates(group)

        self.assertEqual(recommendations[0]['student_id'], strong.student_id)
        self.assertTrue(recommendations[0]['reasons'])
        self.assertIn('Frontend', recommendations[0]['reasons'][0])
        self.assertGreater(recommendations[0]['gap_score'], 0)

    def test_recommendations_exclude_students_already_in_a_group(self):
        self._student(1, {self.backend: 3})
        assigned = self._student(2, {self.frontend: 3})
        group = Group.objects.create(project=self.project, group_name='Team')
        GroupMember.objects.create(group=group, student=assigned)

        recommendations = recommend_candidates(group)

        self.assertEqual(
            [r['student_id'] for r in recommendations],
            [self.students[0].student_id],
        )

    def test_formation_endpoints_require_authentication(self):
        for url in [
            reverse('students:group_automate_ajax'),
            reverse('students:group_automate_save_ajax'),
        ]:
            with self.subTest(url=url):
                response = self.client.post(url, {'project_id': self.project.project_id})
                self.assertEqual(response.status_code, 302)
                self.assertIn('next=', response['Location'])

    def test_formation_preview_and_save_for_manager(self):
        from apps.core.roles import ROLE_INSTRUCTOR, set_role

        instructor = User.objects.create_user(username='instructor7', password='secret1234')
        set_role(instructor, ROLE_INSTRUCTOR)
        self.client.force_login(instructor)

        for i in range(4):
            self._student(i + 1, {self.backend: 3})

        payload = {'project_id': self.project.project_id, 'max_members': 2}
        preview = self.client.post(reverse('students:group_automate_ajax'), payload)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()['ok'])
        self.assertEqual(preview.json()['group_count'], 2)
        self.assertEqual(Group.objects.count(), 0)  # preview writes nothing

        saved = self.client.post(reverse('students:group_automate_save_ajax'), payload)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['created'], 2)
        self.assertEqual(Group.objects.count(), 2)
        self.assertEqual(GroupMember.objects.count(), 4)

    def test_formation_rejects_invalid_parameters(self):
        from apps.core.roles import ROLE_INSTRUCTOR, set_role

        instructor = User.objects.create_user(username='instructor8', password='secret1234')
        set_role(instructor, ROLE_INSTRUCTOR)
        self.client.force_login(instructor)

        cases = [
            {},
            {'project_id': 'not-a-number'},
            {'project_id': self.project.project_id, 'max_members': '99'},
            {'project_id': self.project.project_id, 'group_count': '0'},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post(
                    reverse('students:group_automate_ajax'), payload
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())

    def test_formation_rejects_group_count_above_half_the_pool(self):
        self._login_instructor('formation-half-pool')
        for i in range(5):
            self._student(i + 1, {self.backend: 3})

        payload = {'project_id': self.project.project_id, 'group_count': 3}
        for url_name in self._formation_urls():
            with self.subTest(url=url_name):
                response = self.client.post(reverse(url_name), payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('cannot exceed 2', response.json()['error'])
                self.assertEqual(Group.objects.count(), 0)

    def test_formation_rejects_group_count_equal_to_eligible_students(self):
        self._login_instructor('formation-singletons')
        for i in range(4):
            self._student(i + 1, {self.backend: 3})

        payload = {'project_id': self.project.project_id, 'group_count': 4}
        for url_name in self._formation_urls():
            with self.subTest(url=url_name):
                response = self.client.post(reverse(url_name), payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(
                    'at least 2 members', response.json()['error']
                )
                self.assertEqual(Group.objects.count(), 0)

    def test_formation_rejects_group_count_above_ten(self):
        self._login_instructor('formation-too-large')
        for i in range(6):
            self._student(i + 1, {self.backend: 3})

        for group_count in (11, 10000000):
            payload = {
                'project_id': self.project.project_id,
                'group_count': group_count,
            }
            for url_name in self._formation_urls():
                with self.subTest(group_count=group_count, url=url_name):
                    response = self.client.post(reverse(url_name), payload)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(
                        response.json()['error'],
                        'Number of groups cannot exceed 10.',
                    )
                    self.assertEqual(Group.objects.count(), 0)

    def test_group_page_eligible_count_is_global(self):
        self._login_instructor('formation-eligible-count')
        students = [
            self._student(index + 1, {self.backend: 3}) for index in range(3)
        ]
        other_project = Project.objects.create(project_name='Other Project')
        other_group = Group.objects.create(
            project=other_project, group_name='Other Group'
        )
        GroupMember.objects.create(group=other_group, student=students[0])

        response = self.client.get(reverse('students:group_list'))

        self.assertEqual(response.status_code, 200)
        projects = {
            project.project_id: project
            for project in response.context['all_projects']
        }
        self.assertEqual(projects[self.project.project_id].eligible_count, 2)
        self.assertEqual(projects[other_project.project_id].eligible_count, 2)

    def test_formation_group_limit_uses_only_eligible_students(self):
        self._login_instructor('formation-eligible-only')
        students = [
            self._student(i + 1, {self.backend: 3}) for i in range(6)
        ]
        existing = Group.objects.create(
            project=self.project, group_name='Existing Group'
        )
        for student in students[:2]:
            GroupMember.objects.create(group=existing, student=student)

        too_many = {'project_id': self.project.project_id, 'group_count': 3}
        rejected = self.client.post(
            reverse('students:group_automate_ajax'), too_many
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn('cannot exceed 2', rejected.json()['error'])

        accepted = self.client.post(
            reverse('students:group_automate_ajax'),
            {'project_id': self.project.project_id, 'group_count': 2},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()['group_count'], 2)
        self.assertEqual(
            sorted(g['size'] for g in accepted.json()['groups']), [2, 2]
        )

    def test_formation_accepts_maximum_even_pool_and_saves(self):
        self._login_instructor('formation-even-pool')
        for i in range(6):
            self._student(i + 1, {self.backend: 3})

        payload = {
            'project_id': self.project.project_id,
            'group_count': 3,
            'max_members': 5,
        }
        preview = self.client.post(
            reverse('students:group_automate_ajax'), payload
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()['group_count'], 3)
        preview_sizes = [g['size'] for g in preview.json()['groups']]
        self.assertEqual(preview_sizes, [2, 2, 2])
        self.assertTrue(all(2 <= size <= 5 for size in preview_sizes))
        self.assertEqual(Group.objects.count(), 0)

        saved = self.client.post(
            reverse('students:group_automate_save_ajax'), payload
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['created'], 3)
        saved_sizes = [
            group.members.count()
            for group in Group.objects.filter(project=self.project)
        ]
        self.assertEqual(saved_sizes, [2, 2, 2])
        self.assertTrue(all(2 <= size <= 5 for size in saved_sizes))

    def test_formation_accepts_ten_groups_and_saves(self):
        self._login_instructor('formation-ten-groups')
        for i in range(20):
            self._student(i + 1, {self.backend: 3})

        payload = {
            'project_id': self.project.project_id,
            'group_count': 10,
            'max_members': 5,
        }
        preview = self.client.post(
            reverse('students:group_automate_ajax'), payload
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()['group_count'], 10)
        self.assertEqual(
            [group['size'] for group in preview.json()['groups']], [2] * 10
        )
        self.assertEqual(Group.objects.count(), 0)

        saved = self.client.post(
            reverse('students:group_automate_save_ajax'), payload
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['created'], 10)
        self.assertEqual(Group.objects.filter(project=self.project).count(), 10)
        self.assertEqual(
            GroupMember.objects.filter(group__project=self.project).count(), 20
        )

    def test_formation_accepts_maximum_odd_pool_within_allowed_sizes(self):
        self._login_instructor('formation-odd-pool')
        for i in range(7):
            self._student(i + 1, {self.backend: 3})

        response = self.client.post(
            reverse('students:group_automate_ajax'),
            {'project_id': self.project.project_id, 'group_count': 3},
        )
        self.assertEqual(response.status_code, 200)
        sizes = sorted(g['size'] for g in response.json()['groups'])
        self.assertEqual(sizes, [2, 2, 3])
        self.assertTrue(all(2 <= size <= 5 for size in sizes))

    def test_formation_accepts_group_count_below_maximum(self):
        self._login_instructor('formation-below-max')
        for i in range(7):
            self._student(i + 1, {self.backend: 3})

        response = self.client.post(
            reverse('students:group_automate_ajax'),
            {'project_id': self.project.project_id, 'group_count': 2},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['group_count'], 2)
        sizes = [g['size'] for g in response.json()['groups']]
        self.assertTrue(all(2 <= size <= 5 for size in sizes))

    def test_formation_blank_group_count_remains_automatic(self):
        self._login_instructor('formation-blank-count')
        for i in range(6):
            self._student(i + 1, {self.backend: 3})

        response = self.client.post(
            reverse('students:group_automate_ajax'),
            {
                'project_id': self.project.project_id,
                'group_count': '',
                'max_members': 3,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['group_count'], 2)
        self.assertEqual(
            [g['size'] for g in response.json()['groups']], [3, 3]
        )

    def test_formation_blank_group_count_is_capped_at_ten(self):
        self._login_instructor('formation-blank-capped')
        for i in range(21):
            self._student(i + 1, {self.backend: 3})

        response = self.client.post(
            reverse('students:group_automate_ajax'),
            {
                'project_id': self.project.project_id,
                'group_count': '',
                'max_members': 2,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['group_count'], 10)
        self.assertEqual(len(data['groups']), 10)
        self.assertEqual([group['size'] for group in data['groups']], [2] * 10)
        self.assertEqual(len(data['unassigned']), 1)
        self.assertTrue(any('Capacity' in warning for warning in data['warnings']))

    def test_group_page_exposes_maximum_formation_groups(self):
        self._login_instructor('formation-page-limit')

        response = self.client.get(reverse('students:group_list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['max_formation_groups'], 10)
        self.assertContains(response, 'id="auto_group_count"')
        self.assertContains(response, 'max="10"')
        self.assertContains(response, 'data-max-groups="10"')

    def test_students_cannot_save_groups_but_may_preview(self):
        from apps.core.roles import ROLE_STUDENT, set_role

        student_user = User.objects.create_user(username='student7', password='secret1234')
        set_role(student_user, ROLE_STUDENT)
        self.client.force_login(student_user)

        payload = {'project_id': self.project.project_id}

        preview = self.client.post(reverse('students:group_automate_ajax'), payload)
        self.assertIn(preview.status_code, (200, 400))  # read-only access allowed

        saved = self.client.post(reverse('students:group_automate_save_ajax'), payload)
        self.assertEqual(saved.status_code, 403)
        self.assertIn('error', saved.json())
        self.assertEqual(Group.objects.count(), 0)

    def _assignment_status_fixture(self):
        other_project = Project.objects.create(project_name='Other Capstone')
        ProjectRequiredSkill.objects.create(
            project=other_project, skill=self.backend, required_level=3
        )
        in_selected = self._student(1, {self.backend: 3, self.frontend: 3})
        in_other = self._student(2, {self.backend: 3})
        unassigned = self._student(3, {self.frontend: 3})
        selected_group = Group.objects.create(
            project=self.project, group_name='Selected Project Group'
        )
        other_group = Group.objects.create(
            project=other_project, group_name='Other Project Group'
        )
        GroupMember.objects.create(group=selected_group, student=in_selected)
        GroupMember.objects.create(group=other_group, student=in_other)
        return other_project, in_selected, in_other, unassigned

    def test_matching_page_distinguishes_group_assignment_statuses(self):
        other_project, in_selected, in_other, unassigned = (
            self._assignment_status_fixture()
        )
        manager = User.objects.create_user(username='matcher-status', password='secret1234')
        self.client.force_login(manager)

        response = self.client.get(
            reverse('students:matching'), {'project': self.project.project_id}
        )
        self.assertEqual(response.status_code, 200)
        results = {r['student_id']: r for r in response.context['results']}

        self.assertTrue(results[in_selected.student_id]['assigned'])
        self.assertFalse(results[in_selected.student_id]['assigned_elsewhere'])
        self.assertFalse(results[in_other.student_id]['assigned'])
        self.assertTrue(results[in_other.student_id]['assigned_elsewhere'])
        self.assertEqual(
            results[in_other.student_id]['other_project_name'],
            other_project.project_name,
        )
        self.assertFalse(results[unassigned.student_id]['assigned'])
        self.assertFalse(results[unassigned.student_id]['assigned_elsewhere'])

        content = response.content.decode()
        self.assertIn("In This Project's Group", content)
        self.assertIn("In Another Project's Group", content)
        self.assertIn('Unassigned', content)

        self.assertEqual(results[in_selected.student_id]['score'], 100)
        self.assertEqual(results[in_other.student_id]['score'], 50)
        self.assertEqual(results[unassigned.student_id]['score'], 50)
        scores = [r['score'] for r in response.context['results']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_matching_page_assignment_status_tracks_selected_project(self):
        other_project, in_selected, in_other, unassigned = (
            self._assignment_status_fixture()
        )
        manager = User.objects.create_user(username='matcher-switch', password='secret1234')
        self.client.force_login(manager)

        response = self.client.get(
            reverse('students:matching'), {'project': other_project.project_id}
        )
        self.assertEqual(response.status_code, 200)
        results = {r['student_id']: r for r in response.context['results']}

        self.assertFalse(results[in_selected.student_id]['assigned'])
        self.assertTrue(results[in_selected.student_id]['assigned_elsewhere'])
        self.assertTrue(results[in_other.student_id]['assigned'])
        self.assertFalse(results[in_other.student_id]['assigned_elsewhere'])
        self.assertFalse(results[unassigned.student_id]['assigned'])
        self.assertFalse(results[unassigned.student_id]['assigned_elsewhere'])

        scores = [r['score'] for r in response.context['results']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_matching_page_requires_login_and_renders(self):
        self.client.logout()
        anonymous = self.client.get(reverse('students:matching'))
        self.assertEqual(anonymous.status_code, 302)

        manager = User.objects.create_user(username='matcher7', password='secret1234')
        self.client.force_login(manager)
        response = self.client.get(reverse('students:matching'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'students/matching.html')
        self.assertIn('results', response.context)
        self.assertIn('summary', response.context)

    def test_matching_page_scores_are_sorted_best_first(self):
        expert = self._student(1, {self.backend: 5, self.frontend: 5})
        beginner = self._student(2, {self.backend: 1})
        unskilled = self._student(3)  # no skills at all

        manager = User.objects.create_user(username='matcher8', password='secret1234')
        self.client.force_login(manager)
        response = self.client.get(reverse('students:matching'))

        results = response.context['results']
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['student_id'], expert.student_id)
        self.assertEqual(results[0]['score'], 100)
        self.assertEqual(results[1]['student_id'], beginner.student_id)
        self.assertGreater(results[1]['score'], results[2]['score'])
        self.assertEqual(results[2]['student_id'], unskilled.student_id)
        self.assertEqual(results[2]['score'], 0)
        scores = [r['score'] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(response.context['summary']['student_count'], 3)
        self.assertEqual(response.context['summary']['requirement_count'], 2)

    def test_matching_page_reports_requirement_coverage(self):
        self._student(1, {self.backend: 3})
        self._student(2, {self.frontend: 3})

        manager = User.objects.create_user(username='matcher9', password='secret1234')
        self.client.force_login(manager)
        requirements = self.client.get(
            reverse('students:matching')
        ).context['requirements']

        by_skill = {r['skill_name']: r for r in requirements}
        self.assertEqual(by_skill['Backend']['met_count'], 1)
        self.assertEqual(by_skill['Backend']['missing_count'], 1)
        self.assertEqual(by_skill['Backend']['coverage_pct'], 50)

# ---------------------------------------------------------------------------
# No-requirements display and "no remaining gaps" recommendations
# ---------------------------------------------------------------------------

@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed no-requirements tests run only with mysite.test_settings (SQLite).',
)
class NoRequirementsDisplayTests(UnmanagedTablesMixin, TransactionTestCase):
    """A project without required skills must never render as a 100% match.

    ``analyze_group_skills`` reports ``match_percentage``/``weighted_pct`` as
    ``None`` and ``has_requirements=False`` so the group cards, the dashboard
    and the roster modal show "No requirements set" instead of a misleading
    full match. Percentages are unchanged whenever the project does define
    requirements.
    """

    def setUp(self):
        StudentSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        ProjectRequiredSkill.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        Student.objects.all().delete()
        Skill.objects.all().delete()

        self.project = Project.objects.create(project_name='Spec-less Capstone')
        self.group = Group.objects.create(
            project=self.project, group_name='Team Without Spec'
        )
        self.student = Student.objects.create(
            student_number='2026-5001',
            first_name='Nora',
            last_name='Bautista',
            email='nora@example.com',
            course='BSIT',
            section='3A',
            year_level=3,
        )
        GroupMember.objects.create(group=self.group, student=self.student)
        self.manager = User.objects.create_user(
            username='no-requirements-manager', password='secret1234'
        )

    def _login(self):
        self.client.force_login(self.manager)

    def test_analysis_without_requirements_reports_no_percentage(self):
        analysis = analyze_group_skills(self.group)

        self.assertFalse(analysis['has_requirements'])
        self.assertIsNone(analysis['match_percentage'])
        self.assertIsNone(analysis['weighted_pct'])
        self.assertEqual(analysis['total_required'], 0)

        empty = Group.objects.create(
            project=self.project, group_name='Empty Without Spec'
        )
        empty_analysis = analyze_group_skills(empty)
        self.assertIsNone(empty_analysis['match_percentage'])
        self.assertIsNone(empty_analysis['weighted_pct'])

    def test_group_card_shows_no_requirements_instead_of_100_percent(self):
        self._login()
        response = self.client.get(reverse('students:group_list'))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('No requirements set', content)
        self.assertNotIn('100% match', content)
        self.assertNotIn('data-sg-width="100%"', content)

    def test_dashboard_shows_no_requirements_instead_of_100_percent(self):
        self._login()
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        recent = response.context['analyzed_recent']
        self.assertEqual(len(recent), 1)
        self.assertIsNone(recent[0]['analysis']['match_percentage'])
        content = response.content.decode()
        self.assertIn('No requirements set', content)
        self.assertNotIn('data-sg-width="100%"', content)

    def test_roster_modal_payload_and_script_handle_no_requirements(self):
        self._login()
        response = self.client.get(
            reverse('students:group_get_ajax', kwargs={'pk': self.group.group_id})
        )

        self.assertEqual(response.status_code, 200)
        analysis = response.json()['analysis']
        self.assertFalse(analysis['has_requirements'])
        self.assertIsNone(analysis['match_percentage'])
        self.assertIsNone(analysis['weighted_pct'])

        # The modal is filled by JavaScript, which this suite does not execute,
        # so assert the rendered page carries the guarded branch the modal uses.
        page = self.client.get(reverse('students:group_list')).content.decode()
        self.assertIn('if (!analysis.has_requirements)', page)
        self.assertIn("badge.innerText = 'No requirements set';", page)

    def test_analysis_with_requirements_still_scores_normally(self):
        backend = Skill.objects.create(skill_name='Backend')
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=backend, required_level=3
        )
        StudentSkill.objects.create(
            student=self.student, skill=backend, proficiency_level=2
        )

        analysis = analyze_group_skills(self.group)

        self.assertTrue(analysis['has_requirements'])
        self.assertEqual(analysis['match_percentage'], 0)
        self.assertEqual(analysis['deficient_count'], 1)
        # Backend 2 of the required 3 = 67% weighted coverage.
        self.assertEqual(analysis['weighted_pct'], 67)

    def test_zero_required_level_does_not_break_weighting(self):
        backend = Skill.objects.create(skill_name='Backend')
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=backend, required_level=0
        )
        StudentSkill.objects.create(
            student=self.student, skill=backend, proficiency_level=2
        )

        analysis = analyze_group_skills(self.group)

        self.assertTrue(analysis['has_requirements'])
        self.assertEqual(analysis['weighted_pct'], 0)
        self.assertEqual(analysis['match_percentage'], 100)


@skipUnless(
    connection.vendor == 'sqlite',
    'DB-backed recommendation tests run only with mysite.test_settings (SQLite).',
)
class NoRemainingGapRecommendationTests(UnmanagedTablesMixin, TransactionTestCase):
    """A roster that already covers every requirement has no gap-fillers."""

    def setUp(self):
        StudentSkill.objects.all().delete()
        GroupMember.objects.all().delete()
        ProjectRequiredSkill.objects.all().delete()
        Group.objects.all().delete()
        Project.objects.all().delete()
        Student.objects.all().delete()
        Skill.objects.all().delete()

        self.backend = Skill.objects.create(skill_name='Backend')
        self.project = Project.objects.create(project_name='Covered Capstone')
        ProjectRequiredSkill.objects.create(
            project=self.project, skill=self.backend, required_level=3
        )
        self.manager = User.objects.create_user(
            username='no-gap-manager', password='secret1234'
        )

    def _student(self, index, level=None):
        student = Student.objects.create(
            student_number=f'2026-61{index:02d}',
            first_name=f'Student{index}',
            last_name=f'Family{index}',
            email=f'nogap{index}@example.com',
            course='BSIT',
            section='3B',
            year_level=3,
        )
        if level is not None:
            StudentSkill.objects.create(
                student=student, skill=self.backend, proficiency_level=level
            )
        return student

    def _group(self, name, member_level):
        group = Group.objects.create(project=self.project, group_name=name)
        member = self._student(len(name) + member_level * 10, member_level)
        GroupMember.objects.create(group=group, student=member)
        return group

    def test_no_candidates_are_recommended_when_no_gap_remains(self):
        group = self._group('Complete Team', 4)
        self._student(90, 5)  # unassigned and over-qualified

        self.assertEqual(recommend_candidates(group), [])

        self.client.force_login(self.manager)
        response = self.client.get(
            reverse(
                'students:group_recommendations_ajax',
                kwargs={'group_pk': group.group_id},
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['recommendations'], [])

    def test_assigned_students_stay_excluded_when_a_gap_remains(self):
        group = self._group('Needs Backend', 1)
        surplus = self._student(91, 5)
        assigned_elsewhere = self._student(92, 5)
        other_group = Group.objects.create(
            project=self.project, group_name='Other Team'
        )
        GroupMember.objects.create(group=other_group, student=assigned_elsewhere)

        recommendations = recommend_candidates(group)

        self.assertEqual(
            [r['student_id'] for r in recommendations],
            [surplus.student_id],
        )
        self.assertEqual(recommendations[0]['gap_score'], 100)

    def test_gap_fill_score_still_ranks_candidates_when_gaps_exist(self):
        group = self._group('Partially Covered', 1)
        surplus = self._student(93, 5)
        partial = self._student(94, 1)
        self._student(95)  # no recorded proficiency: lowest rank

        recommendations = recommend_candidates(group)
        by_id = {r['student_id']: r for r in recommendations}

        # The member has level 1, so the outstanding deficit is 2 levels.
        self.assertEqual(by_id[surplus.student_id]['gap_score'], 100)
        self.assertEqual(by_id[partial.student_id]['gap_score'], 50)
        self.assertEqual(recommendations[0]['student_id'], surplus.student_id)

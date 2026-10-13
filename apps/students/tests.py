from django.test import SimpleTestCase

from .models import (
    Group,
    GroupMember,
    Project,
    ProjectRequiredSkill,
    Skill,
    Student,
    StudentSkill,
)


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
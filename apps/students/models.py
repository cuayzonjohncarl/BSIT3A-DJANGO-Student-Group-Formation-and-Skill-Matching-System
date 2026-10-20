"""Student Management model mapped onto the pre-existing `students` table.

The `students` table was created outside of Django (raw SQL). The model is
therefore declared with ``managed = False`` so Django never creates, alters,
or drops the table, and no migration is required.
"""

from django.db import models


YEAR_LEVEL_CHOICES = (
    (1, '1st Year'),
    (2, '2nd Year'),
    (3, '3rd Year'),
    (4, '4th Year'),
)


class Student(models.Model):
    student_id = models.AutoField(primary_key=True)
    student_number = models.CharField(max_length=50)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255)
    course = models.CharField(max_length=100)
    section = models.CharField(max_length=50)
    year_level = models.PositiveSmallIntegerField(
        choices=YEAR_LEVEL_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = 'students'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.last_name}, {self.first_name} ({self.student_number})'


class Skill(models.Model):
    skill_id = models.AutoField(primary_key=True)
    skill_name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'skills'
        ordering = ['skill_name']

    def __str__(self):
        return self.skill_name


class StudentSkill(models.Model):
    student_skill_id = models.AutoField(primary_key=True)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='student_skills',
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        db_column='skill_id',
        related_name='student_skills',
    )
    proficiency_level = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'student_skills'
        ordering = ['student', 'skill']

    def __str__(self):
        return f'{self.student} - {self.skill} ({self.proficiency_level})'


class Project(models.Model):
    project_id = models.AutoField(primary_key=True)
    project_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'projects'
        ordering = ['project_name']

    def __str__(self):
        return self.project_name


class ProjectRequiredSkill(models.Model):
    project_skill_id = models.AutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column='project_id',
        related_name='required_skills',
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        db_column='skill_id',
        related_name='project_required_skills',
    )
    required_level = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'project_required_skills'
        ordering = ['project', 'skill']

    def __str__(self):
        return f'{self.project} - {self.skill} ({self.required_level})'


class Group(models.Model):
    group_id = models.AutoField(primary_key=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        db_column='project_id',
        related_name='groups',
    )
    group_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'groups'
        ordering = ['group_name']

    def __str__(self):
        return self.group_name


class GroupMember(models.Model):
    group_member_id = models.AutoField(primary_key=True)
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        db_column='group_id',
        related_name='members',
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        db_column='student_id',
        related_name='group_memberships',
    )

    class Meta:
        managed = False
        db_table = 'group_members'
        ordering = ['group', 'student']

    def __str__(self):
        return f'{self.group} - {self.student}'

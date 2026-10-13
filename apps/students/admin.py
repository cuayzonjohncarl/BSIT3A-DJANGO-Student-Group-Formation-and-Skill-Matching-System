from django.contrib import admin

from .models import (
    Group,
    GroupMember,
    Project,
    ProjectRequiredSkill,
    Skill,
    Student,
    StudentSkill,
)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_number', 'first_name', 'last_name', 'email', 'course', 'section')
    search_fields = ('student_number', 'first_name', 'last_name', 'email', 'course', 'section')


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('skill_id', 'skill_name', 'description')
    search_fields = ('skill_name', 'description')


@admin.register(StudentSkill)
class StudentSkillAdmin(admin.ModelAdmin):
    list_display = ('student_skill_id', 'student', 'skill', 'proficiency_level')
    search_fields = ('student__first_name', 'student__last_name', 'skill__skill_name')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('project_id', 'project_name', 'created_at')
    search_fields = ('project_name', 'description')


@admin.register(ProjectRequiredSkill)
class ProjectRequiredSkillAdmin(admin.ModelAdmin):
    list_display = ('project_skill_id', 'project', 'skill', 'required_level')
    search_fields = ('project__project_name', 'skill__skill_name')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('group_id', 'group_name', 'project', 'created_at')
    search_fields = ('group_name',)


@admin.register(GroupMember)
class GroupMemberAdmin(admin.ModelAdmin):
    list_display = ('group_member_id', 'group', 'student')
    search_fields = ('group__group_name', 'student__first_name', 'student__last_name')

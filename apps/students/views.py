from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models import Q

from .models import (
    Skill,
    Student,
    StudentSkill,
    Project,
    ProjectRequiredSkill,
)


MIN_YEAR_LEVEL = 1
MAX_YEAR_LEVEL = 4
YEAR_LEVEL_SCALE = (
    '1 = 1st Year, 2 = 2nd Year, 3 = 3rd Year, 4 = 4th Year'
)


def _parse_year_level(raw_value):
    """Convert a posted year level to an integer in 1-4, or None when invalid.

    The `students.year_level` column is a nullable integer with no database
    constraint, so the 1-4 range is enforced here. Blank input is handled by the
    caller and represented as None (the field is optional).
    """
    value = (raw_value or '').strip()
    if value == '':
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if MIN_YEAR_LEVEL <= parsed <= MAX_YEAR_LEVEL:
        return parsed
    return None


def _student_data(student):
    """Return the JSON-serializable representation of a student record."""
    return {
        'student_id': student.student_id,
        'student_number': student.student_number,
        'first_name': student.first_name,
        'last_name': student.last_name,
        'email': student.email,
        'course': student.course,
        'section': student.section,
        'year_level': student.year_level,
        'year_level_display': student.get_year_level_display() or '',
    }


@login_required(login_url='login')
def student_list_page(request):
    """Render the searchable, paginated student list."""
    query = request.GET.get('q', '').strip()

    students_list = Student.objects.all()

    if query:
        filters = (
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(course__icontains=query) |
            Q(section__icontains=query)
        )
        # year_level is an integer column, so it is matched only for numeric
        # queries using an exact lookup rather than a text comparison.
        if query.isdigit():
            filters |= Q(year_level=int(query))
        students_list = students_list.filter(filters)

    paginator = Paginator(students_list, 10)
    page_number = request.GET.get('page', 1)
    students = paginator.get_page(page_number)

    return render(request, 'students/list.html', {
        'students': students,
        'query': query,
    })


@login_required(login_url='login')
def student_list_ajax(request):
    """Return the filtered student records as paginated JSON."""
    query = request.GET.get('q', '').strip()

    students_list = Student.objects.all()

    if query:
        filters = (
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(course__icontains=query) |
            Q(section__icontains=query)
        )
        # year_level is an integer column, so it is matched only for numeric
        # queries using an exact lookup rather than a text comparison.
        if query.isdigit():
            filters |= Q(year_level=int(query))
        students_list = students_list.filter(filters)

    paginator = Paginator(students_list, 10)
    page_number = request.GET.get('page', 1)
    students = paginator.get_page(page_number)
    data = [
        _student_data(s)
        for s in students.object_list
    ]
    return JsonResponse({
        'data': data,
        'has_next': students.has_next(),
        'has_prev': students.has_previous(),
        'page': students.number,
        'pages': students.paginator.num_pages,
        'total': students.paginator.count,
    })


@login_required(login_url='login')
def student_get_ajax(request, pk):
    """Return a single student record as JSON."""
    student = get_object_or_404(Student, pk=pk)
    return JsonResponse(_student_data(student))


@login_required(login_url='login')
@require_POST
def student_save_ajax(request):
    """Validate and create or update a student record, returning its data as JSON."""
    student_id = request.POST.get('student_id')

    if student_id:
        student = get_object_or_404(Student, pk=student_id)
        is_update = True
    else:
        student = Student()
        is_update = False

    student_number = request.POST.get('student_number', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    course = request.POST.get('course', '').strip()
    section = request.POST.get('section', '').strip()
    year_level_raw = request.POST.get('year_level', '').strip()

    if not student_number:
        return JsonResponse({'error': 'Student number is required.'}, status=400)

    if not first_name:
        return JsonResponse({'error': 'First name is required.'}, status=400)

    if not last_name:
        return JsonResponse({'error': 'Last name is required.'}, status=400)

    if not email:
        return JsonResponse({'error': 'Email is required.'}, status=400)

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'error': 'Enter a valid email address.'}, status=400)

    if not course:
        return JsonResponse({'error': 'Course is required.'}, status=400)

    if not section:
        return JsonResponse({'error': 'Section is required.'}, status=400)

    # Year level is optional: an empty value is stored as NULL. Any non-empty
    # value must be a whole number within the 1-4 range.
    year_level = None
    if year_level_raw != '':
        year_level = _parse_year_level(year_level_raw)
        if year_level is None:
            return JsonResponse(
                {'error': (
                    f'Year level must be between {MIN_YEAR_LEVEL} and '
                    f'{MAX_YEAR_LEVEL} ({YEAR_LEVEL_SCALE}).'
                )},
                status=400
            )

    duplicates = Student.objects.filter(student_number=student_number)
    if student.pk:
        duplicates = duplicates.exclude(pk=student.pk)
    if duplicates.exists():
        return JsonResponse(
            {'error': 'A student with that student number already exists.'},
            status=400
        )

    student.student_number = student_number
    student.first_name = first_name
    student.last_name = last_name
    student.email = email
    student.course = course
    student.section = section
    student.year_level = year_level

    try:
        student.save()
    except IntegrityError:
        return JsonResponse(
            {'error': 'Could not save record due to a conflict.'},
            status=400
        )

    messages.success(
        request,
        f'Student "{student.first_name} {student.last_name}" has been '
        f'{"updated" if is_update else "saved"} successfully.'
    )

    payload = {'status': 'success'}
    payload.update(_student_data(student))
    return JsonResponse(payload)


@login_required(login_url='login')
@require_POST
def student_delete_ajax(request, pk):
    """Delete the specified student record and confirm as JSON."""
    student = get_object_or_404(Student, pk=pk)
    student_name = f'{student.first_name} {student.last_name}'
    student.delete()
    messages.success(request, f'Student "{student_name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


# ---------------------------------------------------------------------------
# Skills management
# ---------------------------------------------------------------------------

def _parse_int(raw_value):
    """Convert a posted value to an integer, returning None when invalid."""
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _skill_data(skill):
    """Return the JSON-serializable representation of a skill record."""
    return {
        'skill_id': skill.skill_id,
        'skill_name': skill.skill_name,
        'description': skill.description or '',
    }


@login_required(login_url='login')
def skill_list_page(request):
    """Render the searchable, paginated skill list."""
    query = request.GET.get('q', '').strip()

    skills_list = Skill.objects.all()

    if query:
        skills_list = skills_list.filter(
            Q(skill_name__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(skills_list, 10)
    page_number = request.GET.get('page', 1)
    skills = paginator.get_page(page_number)

    return render(request, 'students/skills.html', {
        'skills': skills,
        'query': query,
    })


@login_required(login_url='login')
def skill_list_ajax(request):
    """Return the filtered skill records as paginated JSON."""
    query = request.GET.get('q', '').strip()

    skills_list = Skill.objects.all()

    if query:
        skills_list = skills_list.filter(
            Q(skill_name__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(skills_list, 10)
    page_number = request.GET.get('page', 1)
    skills = paginator.get_page(page_number)
    data = [_skill_data(s) for s in skills.object_list]
    return JsonResponse({
        'data': data,
        'has_next': skills.has_next(),
        'has_prev': skills.has_previous(),
        'page': skills.number,
        'pages': skills.paginator.num_pages,
        'total': skills.paginator.count,
    })


@login_required(login_url='login')
def skill_get_ajax(request, pk):
    """Return a single skill record as JSON."""
    skill = get_object_or_404(Skill, pk=pk)
    return JsonResponse(_skill_data(skill))


@login_required(login_url='login')
@require_POST
def skill_save_ajax(request):
    """Validate and create or update a skill record, returning its data as JSON."""
    skill_id = request.POST.get('skill_id')

    if skill_id:
        skill_pk = _parse_int(skill_id)
        if skill_pk is None:
            return JsonResponse({'error': 'Invalid skill reference.'}, status=400)
        skill = get_object_or_404(Skill, pk=skill_pk)
        is_update = True
    else:
        skill = Skill()
        is_update = False

    skill_name = request.POST.get('skill_name', '').strip()
    description = request.POST.get('description', '').strip()

    if not skill_name:
        return JsonResponse({'error': 'Skill name is required.'}, status=400)

    # The `skills` table has no unique constraint on skill_name, so duplicate
    # prevention is enforced here (case-insensitively) rather than in the schema.
    duplicates = Skill.objects.filter(skill_name__iexact=skill_name)
    if skill.pk:
        duplicates = duplicates.exclude(pk=skill.pk)
    if duplicates.exists():
        return JsonResponse(
            {'error': 'A skill with that name already exists.'},
            status=400
        )

    skill.skill_name = skill_name
    skill.description = description or None

    try:
        skill.save()
    except IntegrityError:
        return JsonResponse(
            {'error': 'Could not save record due to a conflict.'},
            status=400
        )

    messages.success(
        request,
        f'Skill "{skill.skill_name}" has been '
        f'{"updated" if is_update else "saved"} successfully.'
    )

    payload = {'status': 'success'}
    payload.update(_skill_data(skill))
    return JsonResponse(payload)


@login_required(login_url='login')
@require_POST
def skill_delete_ajax(request, pk):
    """Delete the specified skill record and confirm as JSON."""
    skill = get_object_or_404(Skill, pk=pk)

    # The student_skills and project_required_skills foreign keys are RESTRICT,
    # so a skill that is still referenced cannot be deleted. Report it clearly
    # instead of letting the database raise an error.
    if skill.student_skills.exists():
        return JsonResponse(
            {'error': 'This skill is assigned to students. Remove those '
                      'assignments before deleting it.'},
            status=400
        )

    if skill.project_required_skills.exists():
        return JsonResponse(
            {'error': 'This skill is required by a project. Remove those '
                      'requirements before deleting it.'},
            status=400
        )

    skill_name = skill.skill_name
    skill.delete()
    messages.success(request, f'Skill "{skill_name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


# ---------------------------------------------------------------------------
# Student-skill management
# ---------------------------------------------------------------------------

MIN_PROFICIENCY_LEVEL = 1
MAX_PROFICIENCY_LEVEL = 5
PROFICIENCY_LEVEL_SCALE = (
    '1 = Beginner, 2 = Basic, 3 = Intermediate, 4 = Advanced, 5 = Expert'
)


def _parse_proficiency(raw_value):
    """Convert a posted proficiency value to an integer, or None when invalid.

    The `student_skills.proficiency_level` column is a plain integer with no
    range or enumeration constraint, so only numeric validity is enforced here.
    """
    return _parse_int(raw_value)


def _student_skill_data(student_skill):
    """Return the JSON-serializable representation of a student-skill record."""
    return {
        'student_skill_id': student_skill.student_skill_id,
        'student_id': student_skill.student_id,
        'student_name': (
            f'{student_skill.student.last_name}, {student_skill.student.first_name}'
        ),
        'student_number': student_skill.student.student_number,
        'skill_id': student_skill.skill_id,
        'skill_name': student_skill.skill.skill_name,
        'proficiency_level': student_skill.proficiency_level,
    }


@login_required(login_url='login')
def student_skill_list_page(request):
    """Render the searchable, paginated student-skill assignment list."""
    query = request.GET.get('q', '').strip()

    assignments_list = StudentSkill.objects.select_related('student', 'skill')

    if query:
        assignments_list = assignments_list.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__student_number__icontains=query) |
            Q(skill__skill_name__icontains=query)
        )

    paginator = Paginator(assignments_list, 10)
    page_number = request.GET.get('page', 1)
    assignments = paginator.get_page(page_number)

    return render(request, 'students/student_skills.html', {
        'assignments': assignments,
        'query': query,
        'all_students': Student.objects.all(),
        'all_skills': Skill.objects.all(),
    })


@login_required(login_url='login')
def student_skill_list_ajax(request):
    """Return the filtered student-skill records as paginated JSON."""
    query = request.GET.get('q', '').strip()

    assignments_list = StudentSkill.objects.select_related('student', 'skill')

    if query:
        assignments_list = assignments_list.filter(
            Q(student__first_name__icontains=query) |
            Q(student__last_name__icontains=query) |
            Q(student__student_number__icontains=query) |
            Q(skill__skill_name__icontains=query)
        )

    paginator = Paginator(assignments_list, 10)
    page_number = request.GET.get('page', 1)
    assignments = paginator.get_page(page_number)
    data = [_student_skill_data(a) for a in assignments.object_list]
    return JsonResponse({
        'data': data,
        'has_next': assignments.has_next(),
        'has_prev': assignments.has_previous(),
        'page': assignments.number,
        'pages': assignments.paginator.num_pages,
        'total': assignments.paginator.count,
    })


@login_required(login_url='login')
def student_skill_get_ajax(request, pk):
    """Return a single student-skill assignment as JSON."""
    assignment = get_object_or_404(
        StudentSkill.objects.select_related('student', 'skill'), pk=pk
    )
    return JsonResponse(_student_skill_data(assignment))


@login_required(login_url='login')
@require_POST
def student_skill_save_ajax(request):
    """Validate and create or update a student-skill assignment as JSON."""
    assignment_id = request.POST.get('student_skill_id')

    if assignment_id:
        assignment_pk = _parse_int(assignment_id)
        if assignment_pk is None:
            return JsonResponse({'error': 'Invalid assignment reference.'}, status=400)
        assignment = get_object_or_404(StudentSkill, pk=assignment_pk)
        is_update = True
    else:
        assignment = StudentSkill()
        is_update = False

    student_id = request.POST.get('student_id', '').strip()
    skill_id = request.POST.get('skill_id', '').strip()
    proficiency_raw = request.POST.get('proficiency_level', '').strip()

    if not student_id:
        return JsonResponse({'error': 'Please select a student.'}, status=400)

    if not skill_id:
        return JsonResponse({'error': 'Please select a skill.'}, status=400)

    if proficiency_raw == '':
        return JsonResponse({'error': 'Proficiency level is required.'}, status=400)

    proficiency = _parse_proficiency(proficiency_raw)
    if proficiency is None:
        return JsonResponse(
            {'error': 'Proficiency level must be a whole number.'},
            status=400
        )

    if not MIN_PROFICIENCY_LEVEL <= proficiency <= MAX_PROFICIENCY_LEVEL:
        return JsonResponse(
            {'error': (
                f'Proficiency level must be between {MIN_PROFICIENCY_LEVEL} '
                f'and {MAX_PROFICIENCY_LEVEL} ({PROFICIENCY_LEVEL_SCALE}).'
            )},
            status=400
        )

    student_pk = _parse_int(student_id)
    if student_pk is None:
        return JsonResponse({'error': 'Invalid student reference.'}, status=400)

    skill_pk = _parse_int(skill_id)
    if skill_pk is None:
        return JsonResponse({'error': 'Invalid skill reference.'}, status=400)

    student = get_object_or_404(Student, pk=student_pk)
    skill = get_object_or_404(Skill, pk=skill_pk)

    # The student_skills table has no unique constraint on (student_id,
    # skill_id), so duplicate assignments are prevented here instead.
    duplicates = StudentSkill.objects.filter(student=student, skill=skill)
    if assignment.pk:
        duplicates = duplicates.exclude(pk=assignment.pk)
    if duplicates.exists():
        return JsonResponse(
            {'error': 'That skill is already assigned to the selected student.'},
            status=400
        )

    assignment.student = student
    assignment.skill = skill
    assignment.proficiency_level = proficiency

    try:
        assignment.save()
    except IntegrityError:
        return JsonResponse(
            {'error': 'Could not save assignment due to a conflict.'},
            status=400
        )

    messages.success(
        request,
        f'Skill "{skill.skill_name}" for "{student.first_name} {student.last_name}" '
        f'has been {"updated" if is_update else "assigned"} successfully.'
    )

    payload = {'status': 'success'}
    payload.update(_student_skill_data(assignment))
    return JsonResponse(payload)


@login_required(login_url='login')
@require_POST
def student_skill_delete_ajax(request, pk):
    """Delete the specified student-skill assignment and confirm as JSON."""
    assignment = get_object_or_404(
        StudentSkill.objects.select_related('student', 'skill'), pk=pk
    )
    label = (
        f'{assignment.student.last_name}, {assignment.student.first_name}'
        f' - {assignment.skill.skill_name}'
    )
    assignment.delete()
    messages.success(request, f'Assignment "{label}" has been removed successfully.')
    return JsonResponse({'status': 'deleted'})


# ---------------------------------------------------------------------------
# Project management
# ---------------------------------------------------------------------------


def _project_data(project):
    """Return the JSON-serializable representation of a project record."""
    return {
        'project_id': project.project_id,
        'project_name': project.project_name,
        'description': project.description or '',
    }


@login_required(login_url='login')
def project_list_page(request):
    """Render the searchable, paginated project list."""
    query = request.GET.get('q', '').strip()

    projects_list = Project.objects.all()

    if query:
        projects_list = projects_list.filter(
            Q(project_name__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(projects_list, 10)
    page_number = request.GET.get('page', 1)
    projects = paginator.get_page(page_number)

    return render(request, 'students/projects.html', {
        'projects': projects,
        'query': query,
    })


@login_required(login_url='login')
def project_list_ajax(request):
    """Return the filtered project records as paginated JSON."""
    query = request.GET.get('q', '').strip()

    projects_list = Project.objects.all()

    if query:
        projects_list = projects_list.filter(
            Q(project_name__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(projects_list, 10)
    page_number = request.GET.get('page', 1)
    projects = paginator.get_page(page_number)
    data = [_project_data(p) for p in projects.object_list]
    return JsonResponse({
        'data': data,
        'has_next': projects.has_next(),
        'has_prev': projects.has_previous(),
        'page': projects.number,
        'pages': projects.paginator.num_pages,
        'total': projects.paginator.count,
    })


@login_required(login_url='login')
def project_get_ajax(request, pk):
    """Return a single project record as JSON."""
    project = get_object_or_404(Project, pk=pk)
    return JsonResponse(_project_data(project))


@login_required(login_url='login')
@require_POST
def project_save_ajax(request):
    """Validate and create or update a project record, returning its data as JSON."""
    project_id = request.POST.get('project_id')

    if project_id:
        project_pk = _parse_int(project_id)
        if project_pk is None:
            return JsonResponse({'error': 'Invalid project reference.'}, status=400)
        project = get_object_or_404(Project, pk=project_pk)
        is_update = True
    else:
        project = Project()
        is_update = False

    project_name = request.POST.get('project_name', '').strip()
    description = request.POST.get('description', '').strip()

    if not project_name:
        return JsonResponse({'error': 'Project name is required.'}, status=400)

    duplicates = Project.objects.filter(project_name__iexact=project_name)
    if project.pk:
        duplicates = duplicates.exclude(pk=project.pk)
    if duplicates.exists():
        return JsonResponse(
            {'error': 'A project with that name already exists.'},
            status=400
        )

    project.project_name = project_name
    project.description = description or None

    try:
        project.save()
    except IntegrityError:
        return JsonResponse(
            {'error': 'Could not save record due to a conflict.'},
            status=400
        )

    messages.success(
        request,
        f'Project "{project.project_name}" has been '
        f'{"updated" if is_update else "saved"} successfully.'
    )

    payload = {'status': 'success'}
    payload.update(_project_data(project))
    return JsonResponse(payload)


@login_required(login_url='login')
@require_POST
def project_delete_ajax(request, pk):
    """Delete the specified project record and confirm as JSON."""
    project = get_object_or_404(Project, pk=pk)

    if project.required_skills.exists():
        return JsonResponse(
            {'error': 'This project has required skills. Remove those '
                      'requirements before deleting it.'},
            status=400
        )

    if project.groups.exists():
        return JsonResponse(
            {'error': 'This project has groups. Remove those groups before deleting it.'},
            status=400
        )

    project_name = project.project_name
    project.delete()
    messages.success(request, f'Project "{project_name}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


# ---------------------------------------------------------------------------
# Project required skills management
# ---------------------------------------------------------------------------


def _project_skill_data(project_skill):
    """Return the JSON-serializable representation of a project-skill record."""
    return {
        'project_skill_id': project_skill.project_skill_id,
        'project_id': project_skill.project_id,
        'project_name': project_skill.project.project_name,
        'skill_id': project_skill.skill_id,
        'skill_name': project_skill.skill.skill_name,
        'required_level': project_skill.required_level,
    }


@login_required(login_url='login')
def project_skill_list_page(request):
    """Render the searchable, paginated project-skill requirement list."""
    query = request.GET.get('q', '').strip()

    requirements_list = ProjectRequiredSkill.objects.select_related('project', 'skill')

    if query:
        requirements_list = requirements_list.filter(
            Q(project__project_name__icontains=query) |
            Q(skill__skill_name__icontains=query)
        )

    paginator = Paginator(requirements_list, 10)
    page_number = request.GET.get('page', 1)
    requirements = paginator.get_page(page_number)

    return render(request, 'students/project_skills.html', {
        'requirements': requirements,
        'query': query,
        'all_projects': Project.objects.all(),
        'all_skills': Skill.objects.all(),
    })


@login_required(login_url='login')
def project_skill_list_ajax(request):
    """Return the filtered project-skill records as paginated JSON."""
    query = request.GET.get('q', '').strip()

    requirements_list = ProjectRequiredSkill.objects.select_related('project', 'skill')

    if query:
        requirements_list = requirements_list.filter(
            Q(project__project_name__icontains=query) |
            Q(skill__skill_name__icontains=query)
        )

    paginator = Paginator(requirements_list, 10)
    page_number = request.GET.get('page', 1)
    requirements = paginator.get_page(page_number)
    data = [_project_skill_data(r) for r in requirements.object_list]
    return JsonResponse({
        'data': data,
        'has_next': requirements.has_next(),
        'has_prev': requirements.has_previous(),
        'page': requirements.number,
        'pages': requirements.paginator.num_pages,
        'total': requirements.paginator.count,
    })


@login_required(login_url='login')
def project_skill_get_ajax(request, pk):
    """Return a single project-skill requirement as JSON."""
    requirement = get_object_or_404(
        ProjectRequiredSkill.objects.select_related('project', 'skill'), pk=pk
    )
    return JsonResponse(_project_skill_data(requirement))


@login_required(login_url='login')
@require_POST
def project_skill_save_ajax(request):
    """Validate and create or update a project-skill requirement as JSON."""
    requirement_id = request.POST.get('project_skill_id')

    if requirement_id:
        requirement_pk = _parse_int(requirement_id)
        if requirement_pk is None:
            return JsonResponse({'error': 'Invalid requirement reference.'}, status=400)
        requirement = get_object_or_404(ProjectRequiredSkill, pk=requirement_pk)
        is_update = True
    else:
        requirement = ProjectRequiredSkill()
        is_update = False

    project_id = request.POST.get('project_id', '').strip()
    skill_id = request.POST.get('skill_id', '').strip()
    required_level_raw = request.POST.get('required_level', '').strip()

    if not project_id:
        return JsonResponse({'error': 'Please select a project.'}, status=400)

    if not skill_id:
        return JsonResponse({'error': 'Please select a skill.'}, status=400)

    if required_level_raw == '':
        return JsonResponse({'error': 'Required level is required.'}, status=400)

    required_level = _parse_proficiency(required_level_raw)
    if required_level is None:
        return JsonResponse(
            {'error': 'Required level must be a whole number.'},
            status=400
        )

    if not MIN_PROFICIENCY_LEVEL <= required_level <= MAX_PROFICIENCY_LEVEL:
        return JsonResponse(
            {'error': (
                f'Required level must be between {MIN_PROFICIENCY_LEVEL} '
                f'and {MAX_PROFICIENCY_LEVEL} ({PROFICIENCY_LEVEL_SCALE}).'
            )},
            status=400
        )

    project_pk = _parse_int(project_id)
    if project_pk is None:
        return JsonResponse({'error': 'Invalid project reference.'}, status=400)

    skill_pk = _parse_int(skill_id)
    if skill_pk is None:
        return JsonResponse({'error': 'Invalid skill reference.'}, status=400)

    project = get_object_or_404(Project, pk=project_pk)
    skill = get_object_or_404(Skill, pk=skill_pk)

    duplicates = ProjectRequiredSkill.objects.filter(project=project, skill=skill)
    if requirement.pk:
        duplicates = duplicates.exclude(pk=requirement.pk)
    if duplicates.exists():
        return JsonResponse(
            {'error': 'That skill is already required by the selected project.'},
            status=400
        )

    requirement.project = project
    requirement.skill = skill
    requirement.required_level = required_level

    try:
        requirement.save()
    except IntegrityError:
        return JsonResponse(
            {'error': 'Could not save requirement due to a conflict.'},
            status=400
        )

    messages.success(
        request,
        f'Skill "{skill.skill_name}" for project "{project.project_name}" '
        f'has been {"updated" if is_update else "assigned"} successfully.'
    )

    payload = {'status': 'success'}
    payload.update(_project_skill_data(requirement))
    return JsonResponse(payload)


@login_required(login_url='login')
@require_POST
def project_skill_delete_ajax(request, pk):
    """Delete the specified project-skill requirement and confirm as JSON."""
    requirement = get_object_or_404(
        ProjectRequiredSkill.objects.select_related('project', 'skill'), pk=pk
    )
    label = (
        f'{requirement.project.project_name}'
        f' - {requirement.skill.skill_name}'
    )
    requirement.delete()
    messages.success(request, f'Requirement "{label}" has been removed successfully.')
    return JsonResponse({'status': 'deleted'})

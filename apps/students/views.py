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

from .models import Student


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
    }


@login_required(login_url='login')
def student_list_page(request):
    """Render the searchable, paginated student list."""
    query = request.GET.get('q', '').strip()

    students_list = Student.objects.all()

    if query:
        students_list = students_list.filter(
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(course__icontains=query) |
            Q(section__icontains=query)
        )

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
        students_list = students_list.filter(
            Q(student_number__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(course__icontains=query) |
            Q(section__icontains=query)
        )

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

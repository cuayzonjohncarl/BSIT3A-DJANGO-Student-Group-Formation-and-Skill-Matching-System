from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.roles import ROLE_GROUPS, ROLE_STUDENT

User = get_user_model()

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=1)
INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Locked for 1 minute.'


def _reset_lock_state(request):
    request.session['failed_attempts'] = 0
    request.session['lock_time'] = None


def _get_lock_state(request):
    failed_attempts = request.session.get('failed_attempts', 0)
    lock_time = request.session.get('lock_time')

    if not lock_time:
        return failed_attempts, None

    try:
        unlock_time = timezone.datetime.fromisoformat(lock_time)
    except (TypeError, ValueError):
        _reset_lock_state(request)
        return 0, None

    now = timezone.now()
    if now < unlock_time:
        remaining = max(1, int((unlock_time - now).total_seconds()))
        return failed_attempts, remaining

    _reset_lock_state(request)
    return 0, None


def _set_lock_state(request):
    lock_until = timezone.now() + LOCK_DURATION
    request.session['failed_attempts'] = MAX_FAILED_ATTEMPTS
    request.session['lock_time'] = lock_until.isoformat()
    return int(LOCK_DURATION.total_seconds())


def _validate_registration_data(data):
    errors = {}

    username = data.get('username', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username:
        errors['username'] = 'Username is required.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username already taken.'

    if not first_name:
        errors['first_name'] = 'First name is required.'

    if not last_name:
        errors['last_name'] = 'Last name is required.'

    if not email:
        errors['email'] = 'Email is required.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    return errors


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    failed_attempts, remaining = _get_lock_state(request)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    if request.method == 'GET':
        return render(request, 'auth/login.html')

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is not None:
        _reset_lock_state(request)
        login(request, user)
        return redirect('dashboard')

    failed_attempts += 1
    request.session['failed_attempts'] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        remaining = _set_lock_state(request)
        messages.error(request, LOCKED_MESSAGE)
        return render(request, 'auth/login.html', {'locked': True, 'remaining': remaining})

    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def home(request):
    from apps.students.models import (
        Student,
        Skill,
        Project,
        Group,
        ProjectRequiredSkill,
        StudentSkill,
    )
    from apps.students.matching import PROFICIENCY_LABELS
    from apps.students.views import _analyze_group_skills

    total_students = Student.objects.count()
    total_skills = Skill.objects.count()
    total_projects = Project.objects.count()
    total_groups = Group.objects.count()

    # Real counts derived from existing records only - nothing is estimated.
    students_with_skills = Student.objects.filter(
        student_skills__isnull=False
    ).distinct().count()
    total_requirements = ProjectRequiredSkill.objects.count()

    # Aggregate the existing skill-gap analysis across every formed group.
    satisfied_total = 0
    deficient_total = 0
    missing_total = 0
    checks_total = 0
    full_match_groups = 0
    match_sum = 0
    groups_with_requirements = 0
    group_match_series = []
    for group in Group.objects.select_related('project').order_by('group_name'):
        analysis = _analyze_group_skills(group)
        satisfied_total += analysis['satisfied_count']
        deficient_total += analysis['deficient_count']
        missing_total += analysis['missing_count']
        checks_total += analysis['total_required']
        if analysis['total_required']:
            groups_with_requirements += 1
            match_sum += analysis['match_percentage']
            if analysis['match_percentage'] == 100:
                full_match_groups += 1
            group_match_series.append({
                'label': group.group_name,
                'value': analysis['match_percentage'],
            })
    group_match_series = group_match_series[:8]

    coverage_pct = (
        round((satisfied_total / checks_total) * 100) if checks_total else None
    )
    avg_match_pct = (
        round(match_sum / groups_with_requirements)
        if groups_with_requirements else None
    )

    recent_groups = list(Group.objects.select_related('project')[:6])
    analyzed_recent = []
    for g in recent_groups:
        analyzed_recent.append({
            'group': g,
            'analysis': _analyze_group_skills(g),
        })

    # Chart series: every number below is a direct database aggregate.
    proficiency_counts = {
        row['proficiency_level']: row['total']
        for row in StudentSkill.objects.values('proficiency_level').annotate(
            total=Count('student_skill_id')
        )
    }
    proficiency_chart = [
        {
            'label': PROFICIENCY_LABELS[level],
            'count': proficiency_counts.get(level, 0),
        }
        for level in sorted(PROFICIENCY_LABELS)
    ]

    requirement_status_chart = [
        {'label': 'Satisfied', 'value': satisfied_total},
        {'label': 'Deficient', 'value': deficient_total},
        {'label': 'Missing', 'value': missing_total},
    ]

    # ``order_by()`` first: the model's default ordering would otherwise be
    # added to the GROUP BY and split every course into per-student rows.
    course_chart = [
        {'label': row['course'] or 'Unspecified', 'value': row['total']}
        for row in (
            Student.objects.values('course')
            .order_by()
            .annotate(total=Count('student_id'))
            .order_by('-total', 'course')[:6]
        )
    ]

    return render(request, 'home.html', {
        'total_students': total_students,
        'total_skills': total_skills,
        'total_projects': total_projects,
        'total_groups': total_groups,
        'students_with_skills': students_with_skills,
        'total_requirements': total_requirements,
        'satisfied_total': satisfied_total,
        'deficient_total': deficient_total,
        'missing_total': missing_total,
        'checks_total': checks_total,
        'full_match_groups': full_match_groups,
        'groups_with_requirements': groups_with_requirements,
        'coverage_pct': coverage_pct,
        'avg_match_pct': avg_match_pct,
        'analyzed_recent': analyzed_recent,
        'proficiency_chart': proficiency_chart,
        'requirement_status_chart': requirement_status_chart,
        'group_match_series': group_match_series,
        'course_chart': course_chart,
    })


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html')

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)
    if errors:
        return render(request, 'auth/register.html', {'errors': errors, 'form_data': form_data})

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )

    # New self-registered accounts start as Students. Instructors and
    # Administrators are promoted by an administrator on the Users page.
    from django.contrib.auth.models import Group
    role_group, _created = Group.objects.get_or_create(name=ROLE_GROUPS[ROLE_STUDENT])
    user.groups.add(role_group)

    login(request, user)
    return redirect('dashboard')

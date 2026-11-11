from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q

from apps.core.roles import (
    DEFAULT_ROLE,
    ROLE_GROUPS,
    ROLE_LABELS,
    admin_required,
    role_for,
    set_role,
)

VALID_ROLES = tuple(ROLE_GROUPS)


def _requested_role(request):
    """Validate the posted role key.

    Returns ``(role, error)``: ``role`` is ``None`` when the caller did not
    post one, and ``error`` is set when the posted value is unknown.
    """
    role = (request.POST.get('role') or '').strip()
    if not role:
        return None, None
    if role not in VALID_ROLES:
        return None, 'Unknown role.'
    return role, None


def _parse_int(raw_value):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


# PAGE
@login_required(login_url='login')
@admin_required
def user_list_page(request):
    query = request.GET.get('q', '').strip()

    users_list = User.objects.all().order_by('-date_joined')

    if query:
        users_list = users_list.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)

    # Attach the resolved role so the table can show the real authorization
    # level instead of Django's is_staff/is_superuser flags.
    for user in users.object_list:
        user.role = role_for(user) or DEFAULT_ROLE
        user.role_label = ROLE_LABELS.get(user.role, '')

    return render(request, 'users/list.html', {
        'users': users,
        'query': query,
    })


# LIST USERS (AJAX)
@login_required(login_url='login')
@admin_required
def user_list_ajax(request):
    users_list = User.objects.all().order_by('-date_joined')
    paginator = Paginator(users_list, 10)
    page_number = request.GET.get('page', 1)
    users = paginator.get_page(page_number)
    data = [
        {
            'id': u.id,
            'username': u.username,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'email': u.email,
            'is_staff': u.is_staff,
            'is_active': u.is_active,
            'date_joined': u.date_joined,
            'role': role_for(u) or DEFAULT_ROLE,
            'role_label': ROLE_LABELS.get(role_for(u) or DEFAULT_ROLE, ''),
        }
        for u in users.object_list
    ]
    return JsonResponse({
        "data":     data,
        "has_next": users.has_next(),
        "has_prev": users.has_previous(),
        "page":     users.number,
        "pages":    users.paginator.num_pages,
        "total":    users.paginator.count,
    })


# GET SINGLE USER (AJAX)
@login_required(login_url='login')
@admin_required
def user_get_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    role = role_for(user) or DEFAULT_ROLE
    return JsonResponse({
        "id":         user.id,
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "email":      user.email,
        "is_staff":   user.is_staff,
        "is_active":  user.is_active,
        "role":       role,
    })


# CREATE / UPDATE USER (AJAX)
@login_required(login_url='login')
@admin_required
@require_POST
def user_save_ajax(request):
    user_id = request.POST.get("id")

    if user_id:
        user_pk = _parse_int(user_id)
        if user_pk is None:
            return JsonResponse({"error": "Invalid user reference."}, status=400)
        user = get_object_or_404(User, pk=user_pk)
        is_update = True
    else:
        user = User()
        is_update = False

    username = request.POST.get("username", "").strip()
    email = request.POST.get("email", "").strip()

    role, role_error = _requested_role(request)
    if role_error:
        return JsonResponse({"error": role_error}, status=400)

    if not username:
        return JsonResponse({"error": "Username is required."}, status=400)

    dup_qs = User.objects.filter(Q(username=username) | (Q(email=email) & ~Q(email="")))
    if user_id:
        dup_qs = dup_qs.exclude(pk=user_id)
    if dup_qs.filter(username=username).exists():
        return JsonResponse({"error": "That username is already taken."}, status=400)
    if email and dup_qs.filter(email=email).exists():
        return JsonResponse({"error": "That email is already in use."}, status=400)

    user.username   = username
    user.first_name = request.POST.get("first_name", "")
    user.last_name  = request.POST.get("last_name", "")
    user.email      = email
    user.is_staff   = request.POST.get("is_staff") == "true"
    user.is_active  = request.POST.get("is_active") == "true"

    password = request.POST.get("password")
    if password:
        user.set_password(password)
    elif not user_id:
        return JsonResponse({"error": "Password is required for new users."}, status=400)

    try:
        user.save()
    except IntegrityError:
        return JsonResponse({"error": "Could not save user due to a conflict (duplicate username/email)."}, status=400)

    # Role assignment: explicit choice wins, otherwise new users default to
    # Instructor and existing users keep the role they already hold.
    if role is None:
        role = DEFAULT_ROLE if not is_update else (role_for(user) or DEFAULT_ROLE)

    if is_update and user.pk == request.user.pk and role != 'admin':
        return JsonResponse({"error": "You cannot remove your own administrator role."}, status=400)

    set_role(user, role)

    messages.success(
        request,
        f'User "{user.username}" has been {"updated" if is_update else "saved"} successfully.'
    )

    return JsonResponse({
        "status": "success",
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
        "role": role,
        "role_label": ROLE_LABELS.get(role, ''),
    })


# DELETE USER (AJAX)
@login_required(login_url='login')
@admin_required
@require_POST
def user_delete_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
        return JsonResponse({"error": "You cannot delete yourself"}, status=400)
    username = user.username
    user.delete()
    return JsonResponse({
        "status": "deleted",
        "message": f'User "{username}" has been deleted successfully.',
    })
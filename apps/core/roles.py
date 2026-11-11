"""Role-based authorization for the three application roles.

The concept paper requires role-based authorization and session security for
**Administrator**, **Instructor** and **Student** accounts (objective 6).

Roles are stored in Django's built-in ``auth_group`` / ``auth_user_groups``
tables, which already exist in the MariaDB schema, so enabling roles requires
**no schema change**: three groups are used as role containers.

Role resolution (in priority order):

1. ``user.is_superuser`` -> ``admin``
2. membership of the ``Administrator`` group -> ``admin``
3. membership of the ``Instructor`` group -> ``instructor``
4. membership of the ``Student`` group -> ``student``
5. otherwise -> :data:`DEFAULT_ROLE`

Users created **before** roles existed have no group. They keep the exact
capabilities they already had (everything except user management), which is the
``instructor`` role. Accounts created through registration are explicitly placed
in the ``Student`` group.

Authorization is enforced in the views (never only in the template): mutating
endpoints require a manager role and return HTTP 403 for everybody else.
"""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect

ROLE_ADMIN = 'admin'
ROLE_INSTRUCTOR = 'instructor'
ROLE_STUDENT = 'student'

#: Role -> name of the Django group used as its container.
ROLE_GROUPS = {
    ROLE_ADMIN: 'Administrator',
    ROLE_INSTRUCTOR: 'Instructor',
    ROLE_STUDENT: 'Student',
}
GROUP_TO_ROLE = {name: role for role, name in ROLE_GROUPS.items()}

ROLE_LABELS = {
    ROLE_ADMIN: 'Administrator',
    ROLE_INSTRUCTOR: 'Instructor',
    ROLE_STUDENT: 'Student',
}

#: Role assumed for authenticated users that belong to no role group.
DEFAULT_ROLE = ROLE_INSTRUCTOR

#: Roles allowed to create, update or delete academic records.
MANAGER_ROLES = (ROLE_ADMIN, ROLE_INSTRUCTOR)

#: Priority order used when a user belongs to more than one role group.
_ROLE_PRIORITY = (ROLE_ADMIN, ROLE_INSTRUCTOR, ROLE_STUDENT)


def role_for(user):
    """Return the role key of ``user``, or ``None`` for anonymous users."""
    if user is None or not user.is_authenticated:
        return None
    if user.is_superuser:
        return ROLE_ADMIN
    names = set(user.groups.values_list('name', flat=True))
    for role in _ROLE_PRIORITY:
        if ROLE_GROUPS[role] in names:
            return role
    return DEFAULT_ROLE


def role_label(user):
    """Human readable role name for ``user``."""
    return ROLE_LABELS.get(role_for(user), '')


def is_admin(user):
    return role_for(user) == ROLE_ADMIN


def can_manage(user):
    """True when the user may create/update/delete academic records."""
    return role_for(user) in MANAGER_ROLES


def ensure_role_groups():
    """Create the three role groups when they do not exist yet (idempotent)."""
    return {
        role: Group.objects.get_or_create(name=group_name)[0]
        for role, group_name in ROLE_GROUPS.items()
    }


def set_role(user, role):
    """Assign ``role`` to ``user`` by moving them between the role groups.

    Other groups the user belongs to are left untouched. Superusers always
    resolve to ``admin`` regardless of group membership.
    """
    if role not in ROLE_GROUPS:
        raise ValueError(f'Unknown role: {role!r}')
    groups = ensure_role_groups()
    user.groups.remove(*groups.values())
    user.groups.add(groups[role])
    return user


def _is_ajax_like(request):
    """True when the caller expects a JSON error body rather than an HTML page."""
    if '/ajax/' in request.path:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return request.headers.get('Accept', '').startswith('application/json')


def role_required(*roles):
    """Allow the view only for the given roles (superusers are always allowed).

    Must be applied **below** ``@login_required`` so anonymous users are still
    redirected to the login page. Failures raise ``PermissionDenied`` (HTTP 403)
    for pages and return a JSON 403 for AJAX endpoints.
    """
    def decorator(view):
        @wraps(view)
        @login_required(login_url='login')
        def wrapper(request, *args, **kwargs):
            role = role_for(request.user)
            allowed = role == ROLE_ADMIN or role in roles
            if not allowed:
                # Mutations and AJAX callers always get an explicit 403; a
                # plain GET for a page the user cannot open is sent back to
                # the dashboard with an explanation instead of a bare error.
                if _is_ajax_like(request) or request.method != 'GET':
                    if _is_ajax_like(request):
                        return JsonResponse(
                            {'error': 'You do not have permission to perform this action.'},
                            status=403,
                        )
                    raise PermissionDenied(
                        'Your account role does not allow this action.'
                    )
                messages.error(
                    request,
                    'Your account role does not allow access to that page.',
                )
                return redirect('dashboard')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


#: Only administrators may manage user accounts.
admin_required = role_required(ROLE_ADMIN)

#: Administrators and instructors may manage academic records.
manager_required = role_required(ROLE_ADMIN, ROLE_INSTRUCTOR)

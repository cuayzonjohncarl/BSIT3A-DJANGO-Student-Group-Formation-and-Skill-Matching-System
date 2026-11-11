"""Template context for role-aware rendering.

Every value here is derived from :mod:`apps.core.roles`. Templates only use
them to show or hide controls; authorization itself is enforced in the views.
"""

from .roles import ROLE_LABELS, MANAGER_ROLES, is_admin, role_for


def roles(request):
    user = getattr(request, 'user', None)
    role = role_for(user)

    return {
        'user_role': role,
        'user_role_label': ROLE_LABELS.get(role, ''),
        'can_manage': role in MANAGER_ROLES,
        'is_admin': is_admin(user),
    }

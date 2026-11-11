"""Automated balanced group formation (concept paper objective 4).

Given a project, its requirement matrix and the pool of students that are not
yet assigned to any group of that project, :func:`plan_groups` distributes the
students into balanced teams.  The algorithm is **deterministic**: the same
input always produces the same plan, which makes it testable and lets an
instructor reproduce a previewed result exactly on save.

Algorithm
---------
1. **Eligibility** - only students passed in by the view are considered; a
   student that already belongs to a group of this project is never placed
   twice, and a student can only appear in one generated group.
2. **Strength ranking** - for every student and requirement:
   ``earned = L * min(level, L)`` (capped, so holding a level-5 skill for a
   level-3 requirement is not over-credited) and ``met`` = number of
   requirements satisfied. Students are ordered by ``(-met, -earned,
   surname, forename, id)``.
3. **Seeding** - the number of groups is ``ceil(students / max_members)``
   unless the caller asks for a specific count. The strongest ``k`` students
   seed the ``k`` groups (one each), which guarantees every group starts with a
   different strength profile.
4. **Greedy marginal-gain fill** - the remaining students are placed one by
   one into the group where they add the most weighted coverage
   (``sum(L * (min(new, L) - min(best, L)))`` over the requirements). Ties go
   to the smaller group, then the lower group index, so sizes stay even. A
   student only goes to a group that still has a free slot; if every group is
   full the student is reported as *unassigned* rather than silently dropped.
5. **Rebalancing** - a bounded, deterministic pass then tries single moves and
   member swaps between groups. A change is accepted only when it improves the
   objective tuple ``(minimum group coverage, -spread)``, i.e. the weakest
   group gets better or the groups get closer together. Capacity and
   project-level uniqueness are re-checked for every candidate change.
6. **Reporting** - the plan lists every group with its members, coverage and
   still-unmet requirements, plus unassigned students and human-readable
   warnings (empty pools, missing requirements, students without recorded
   skills, capacity overflows).

Nothing is written to the database here; :func:`save_plan` persists an accepted
plan inside one transaction.
"""

import math

from django.db import transaction

from .matching import (
    proficiency_label,
    project_requirements,
    skill_index_for_students,
)
from .models import Group, GroupMember

#: System-wide member cap per group (also enforced by manual member adds).
MAX_GROUP_MEMBERS = 5

#: How many rebalancing passes run before the plan is returned.
MAX_REBALANCE_PASSES = 6


def group_label(index):
    """Human label for a zero-based group index: 0 -> ``Group A``, 26 -> ``Group AA``."""
    label = ''
    value = index + 1
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return f'Group {label}'


def _requirement_weights(requirements):
    """``{skill_id: required_level}`` for the project."""
    return {req['skill_id']: req['required_level'] for req in requirements}


def _earned(levels, weights):
    """Weighted capped proficiency of a ``{skill_id: level}`` map."""
    total = 0
    for skill_id, required in weights.items():
        total += min(levels.get(skill_id, 0), required)
    return total


def _coverage(levels, weights):
    """Weighted coverage percentage (0-100) of a ``{skill_id: level}`` map."""
    denominator = sum(weights.values())
    if denominator == 0:
        return 100
    return int(round(100 * _earned(levels, weights) / denominator))


def _best_levels(member_levels):
    """Merge per-student skill maps into the group's best-per-skill map."""
    best = {}
    for levels in member_levels:
        for skill_id, level in levels.items():
            if level > best.get(skill_id, 0):
                best[skill_id] = level
    return best


def _marginal_gain(best, student_levels, weights):
    """Weighted coverage this student would add to a group (always >= 0)."""
    gain = 0
    for skill_id, required in weights.items():
        before = min(best.get(skill_id, 0), required)
        after = min(max(best.get(skill_id, 0), student_levels.get(skill_id, 0)), required)
        gain += after - before
    return gain


def _student_payload(student, levels, weights):
    """JSON-friendly description of a student inside a plan."""
    skills = [
        {
            'skill_id': skill_id,
            'level': levels.get(skill_id, 0),
            'level_label': proficiency_label(levels.get(skill_id, 0))
            if levels.get(skill_id) else 'Not recorded',
            'meets_requirement': levels.get(skill_id, 0) >= required,
        }
        for skill_id, required in sorted(weights.items())
    ]
    return {
        'student_id': student.student_id,
        'student_number': student.student_number,
        'name': f'{student.last_name}, {student.first_name}',
        'full_name': f'{student.first_name} {student.last_name}',
        'course': student.course,
        'section': student.section,
        'year_level': student.year_level,
        'earned': _earned(levels, weights),
        'skills': skills,
    }


def _unmet_requirements(best, requirements):
    unmet = []
    for req in requirements:
        have = best.get(req['skill_id'], 0)
        if have < req['required_level']:
            unmet.append({
                'skill_name': req['skill_name'],
                'required_level': req['required_level'],
                'best_level': have,
                'status': 'missing' if have <= 0 else 'deficient',
            })
    return unmet


def _group_stats(group_members, weights, requirements):
    best = _best_levels([levels for _, levels in group_members])
    coverage = _coverage(best, weights)
    return {
        'coverage': coverage,
        'best_levels': best,
        'unmet': _unmet_requirements(best, requirements),
        'satisfied_count': sum(
            1 for req in requirements
            if best.get(req['skill_id'], 0) >= req['required_level']
        ),
    }


def _objective(groups, weights):
    """``(minimum coverage, -spread)`` - higher is better."""
    coverages = [
        _group_stats(members, weights, [])['coverage'] for members in groups
    ]
    if not coverages:
        return (0, 0)
    return (min(coverages), -(max(coverages) - min(coverages)))


def _rebalance(groups, weights, max_members):
    """Bounded pass of single moves and swaps that improve the objective."""
    for _ in range(MAX_REBALANCE_PASSES):
        improved = False
        current = _objective(groups, weights)

        # Single moves: student from group i into a group j with a free slot.
        for i in range(len(groups)):
            if improved:
                break
            for j in range(len(groups)):
                if i == j or len(groups[j]) >= max_members:
                    continue
                for m_index in range(len(groups[i])):
                    student, levels = groups[i][m_index]
                    if len(groups[i]) <= 1:
                        break
                    trial = [
                        list(members) for members in groups
                    ]
                    trial[i].pop(m_index)
                    trial[j].append((student, levels))
                    if _objective(trial, weights) > current:
                        groups[:] = trial
                        current = _objective(groups, weights)
                        improved = True
                        break
                if improved:
                    break

        # Swaps: exchange one member between two groups.
        for i in range(len(groups)):
            if improved:
                break
            for j in range(i + 1, len(groups)):
                for a in range(len(groups[i])):
                    for b in range(len(groups[j])):
                        trial = [list(members) for members in groups]
                        trial[i][a], trial[j][b] = trial[j][b], trial[i][a]
                        if _objective(trial, weights) > current:
                            groups[:] = trial
                            current = _objective(groups, weights)
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break

        if not improved:
            break


def plan_groups(project, students, group_count=None, max_members=MAX_GROUP_MEMBERS):
    """Build a balanced group plan for ``project``.

    Returns a JSON-serialisable dict (see the module docstring for the steps).
    ``group_count`` may be ``None`` to derive the number of groups from the
    pool size. No database writes happen here.
    """
    students = list(students)
    warnings = []
    errors = []

    try:
        max_members = int(max_members)
    except (TypeError, ValueError):
        max_members = MAX_GROUP_MEMBERS
    if max_members < 2:
        max_members = 2
    if max_members > MAX_GROUP_MEMBERS:
        warnings.append(
            f'Group size capped at the system limit of {MAX_GROUP_MEMBERS} members.'
        )
        max_members = MAX_GROUP_MEMBERS

    if group_count is not None:
        try:
            group_count = int(group_count)
        except (TypeError, ValueError):
            group_count = None
        if group_count is not None and group_count < 1:
            group_count = None

    requirements = project_requirements(project)
    weights = _requirement_weights(requirements)

    if not requirements:
        warnings.append(
            'This project has no required skills, so groups are balanced on '
            'overall recorded proficiency instead of requirement coverage.'
        )

    student_count = len(students)
    if student_count == 0:
        errors.append(
            'No eligible students are available. Every student is already '
            'assigned to a group for this project, or the student list is empty.'
        )

    if group_count is None:
        group_count = max(1, math.ceil(student_count / max_members)) if student_count else 1
    if student_count and group_count > student_count:
        warnings.append(
            f'Only {student_count} student(s) available, so {group_count} groups '
            f'were reduced to {student_count}.'
        )
        group_count = student_count
    capacity = group_count * max_members
    if student_count > capacity:
        warnings.append(
            f'Capacity for {group_count} group(s) of {max_members} is '
            f'{capacity}; {student_count - capacity} student(s) will remain unassigned.'
        )

    if errors:
        return {
            'ok': False,
            'errors': errors,
            'warnings': warnings,
            'project': {'id': project.project_id, 'name': project.project_name},
            'student_count': student_count,
            'group_count': 0,
            'max_members': max_members,
            'groups': [],
            'unassigned': [],
            'stats': {},
        }

    levels = skill_index_for_students(students)

    students_without_skills = [s for s in students if not levels.get(s.student_id)]
    if students_without_skills:
        warnings.append(
            f'{len(students_without_skills)} student(s) have no recorded skills; '
            'they were distributed to keep the group sizes even.'
        )

    # 2. Deterministic strength ranking.
    ranked = sorted(
        students,
        key=lambda s: (
            -sum(
                1 for skill_id, required in weights.items()
                if levels.get(s.student_id, {}).get(skill_id, 0) >= required
            ),
            -_earned(levels.get(s.student_id, {}), weights),
            s.last_name,
            s.first_name,
            s.student_id,
        ),
    )

    # 3. Seed one strong student per group.
    group_members = []
    for index in range(group_count):
        if index < len(ranked):
            student = ranked[index]
            group_members.append([(student, levels.get(student.student_id, {}))])
        else:
            group_members.append([])

    unassigned = []
    # 4. Greedy marginal-gain fill.
    for student in ranked[group_count:]:
        student_levels = levels.get(student.student_id, {})
        best_options = []
        for index, members in enumerate(group_members):
            if len(members) >= max_members:
                continue
            best = _best_levels([lvl for _, lvl in members])
            gain = _marginal_gain(best, student_levels, weights)
            best_options.append((-gain, len(members), index))

        if not best_options:
            unassigned.append(student)
            continue

        best_options.sort()
        target = best_options[0][2]
        group_members[target].append((student, student_levels))

    # 5. Rebalance for a higher floor and a tighter spread.
    if len(group_members) > 1 and weights:
        _rebalance(group_members, weights, max_members)

    groups_payload = []
    for index, members in enumerate(group_members):
        stats = _group_stats(members, weights, requirements)
        groups_payload.append({
            'label': group_label(index),
            'index': index,
            'size': len(members),
            'coverage': stats['coverage'],
            'satisfied_count': stats['satisfied_count'],
            'unmet': stats['unmet'],
            'members': [
                _student_payload(student, member_levels, weights)
                for student, member_levels in sorted(
                    members,
                    key=lambda pair: (
                        pair[0].last_name, pair[0].first_name, pair[0].student_id
                    )
                )
            ],
        })

    coverages = [g['coverage'] for g in groups_payload]
    stats = {
        'requirements': len(requirements),
        'mean_coverage': int(round(sum(coverages) / len(coverages))) if coverages else 0,
        'min_coverage': min(coverages) if coverages else 0,
        'max_coverage': max(coverages) if coverages else 0,
        'assigned_count': sum(g['size'] for g in groups_payload),
        'unassigned_count': len(unassigned),
        'students_without_skills': len(students_without_skills),
    }

    return {
        'ok': True,
        'errors': [],
        'warnings': warnings,
        'project': {'id': project.project_id, 'name': project.project_name},
        'student_count': student_count,
        'group_count': len(groups_payload),
        'max_members': max_members,
        'groups': groups_payload,
        'unassigned': [
            _student_payload(student, levels.get(student.student_id, {}), weights)
            for student in sorted(
                unassigned, key=lambda s: (s.last_name, s.first_name, s.student_id)
            )
        ],
        'stats': stats,
    }


def _unique_group_name(project, label):
    """Append a counter when ``label`` is already used inside this project."""
    name = label
    suffix = 2
    while Group.objects.filter(project=project, group_name__iexact=name).exists():
        name = f'{label} ({suffix})'
        suffix += 1
    return name


@transaction.atomic
def save_plan(project, plan):
    """Persist an accepted plan: create the groups and their memberships.

    Only the plan produced by :func:`plan_groups` for this same project is
    written; memberships are de-duplicated so a student can never end up in two
    generated groups. Returns the created ``Group`` queryset ids.
    """
    created_group_ids = []
    seen_students = set()

    for group_payload in plan.get('groups', []):
        group = Group.objects.create(
            project=project,
            group_name=_unique_group_name(project, group_payload['label']),
        )
        created_group_ids.append(group.group_id)
        for member in group_payload['members']:
            student_id = member['student_id']
            if student_id in seen_students:
                continue
            GroupMember.objects.create(group=group, student_id=student_id)
            seen_students.add(student_id)

    return created_group_ids

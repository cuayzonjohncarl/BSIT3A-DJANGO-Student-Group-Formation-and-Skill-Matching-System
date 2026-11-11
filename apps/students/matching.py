"""Algorithmic skill matching engine (concept paper objective 3).

This module computes **explainable, deterministic** compatibility numbers
between student skill inventories and project requirement matrices.  Nothing in
here is random or hard-coded: every score is derived from the recorded
proficiency levels (1-5) stored in ``student_skills`` and the minimum levels
stored in ``project_required_skills``.

Definitions
-----------
For a project with requirements ``r_i = (skill s_i, required level L_i)``
(``L_i > 0``) and a student whose proficiency in ``s_i`` is ``p_i``
(``0`` when the skill was never recorded):

* **achievement** ``a_i = min(p_i / L_i, 1)`` - full credit is capped at 1.0,
  so over-qualification never inflates a score beyond 100%.
* **weighted coverage** ``C = sum(L_i * a_i) / sum(L_i)`` - harder
  requirements weigh more, which keeps the index honest.
* **compatibility index** = ``round(100 * C)`` - an integer 0-100.

Per requirement the status is one of:

===============  =========================================
``met``          ``p_i >= L_i``
``deficient``    ``0 < p_i < L_i``
``missing``       no proficiency recorded for that skill
===============  =========================================

Because ``C`` is a weighted mean of capped ratios, the same inputs always
produce the same number and every requirement's contribution can be shown to
the user.
"""

from .models import GroupMember, ProjectRequiredSkill, StudentSkill

PROFICIENCY_MIN = 1
PROFICIENCY_MAX = 5

#: Canonical five-point proficiency scale used by the whole application.
PROFICIENCY_LABELS = {
    1: 'Beginner',
    2: 'Elementary',
    3: 'Intermediate',
    4: 'Advanced',
    5: 'Expert',
}

STATUS_MET = 'met'
STATUS_DEFICIENT = 'deficient'
STATUS_MISSING = 'missing'


def proficiency_label(level):
    """Human readable label for a proficiency level (``Level {n}`` if unknown)."""
    return PROFICIENCY_LABELS.get(level, f'Level {level}')


def proficiency_scale_text():
    """The scale rendered in form hints and validation errors."""
    return ', '.join(
        f'{value} = {PROFICIENCY_LABELS[value]}'
        for value in sorted(PROFICIENCY_LABELS)
    )


def project_requirements(project):
    """Return the project's requirements ordered by skill name.

    Each entry is a dict with ``skill_id``, ``skill_name`` and ``required_level``.
    """
    return [
        {
            'skill_id': req.skill_id,
            'skill_name': req.skill.skill_name,
            'required_level': req.required_level,
        }
        for req in ProjectRequiredSkill.objects.filter(project=project)
        .select_related('skill')
        .order_by('skill__skill_name', 'skill_id')
    ]


def skill_index_for_students(students):
    """Return ``{student_id: {skill_id: highest recorded proficiency}}``.

    Duplicate assignments (the schema has no unique constraint) collapse to the
    highest level so the result is stable regardless of insertion order.
    """
    index = {student.student_id: {} for student in students}
    student_ids = list(index)
    if not student_ids:
        return index
    for record in StudentSkill.objects.filter(student_id__in=student_ids):
        levels = index[record.student_id]
        skill_id = record.skill_id
        if skill_id not in levels or record.proficiency_level > levels[skill_id]:
            levels[skill_id] = record.proficiency_level
    return index


def _status_for(have, required):
    if have <= 0:
        return STATUS_MISSING
    return STATUS_MET if have >= required else STATUS_DEFICIENT


def match_student_to_requirements(student, levels, requirements):
    """Score one student against a requirement matrix.

    ``levels`` is ``{skill_id: proficiency}`` for that student (see
    :func:`skill_index_for_students`) and ``requirements`` comes from
    :func:`project_requirements`.

    Returns a dict containing the compatibility ``score`` (0-100), counts for
    every status, the per-requirement ``details`` (including each
    contribution) and a plain-language ``explanation``.
    """
    details = []
    met = deficient = missing = 0
    weighted_earned = 0.0
    weighted_total = 0.0

    for req in requirements:
        required = req['required_level']
        have = levels.get(req['skill_id'], 0)
        status = _status_for(have, required)

        achievement = 1.0 if status == STATUS_MET else (
            (have / required) if required > 0 else 1.0
        )
        contribution = required * achievement
        weighted_total += required
        weighted_earned += contribution

        if status == STATUS_MET:
            met += 1
        elif status == STATUS_DEFICIENT:
            deficient += 1
        else:
            missing += 1

        details.append({
            'skill_id': req['skill_id'],
            'skill_name': req['skill_name'],
            'required_level': required,
            'required_label': proficiency_label(required),
            'have': have,
            'have_label': proficiency_label(have) if have else 'Not recorded',
            'status': status,
            'gap': 0 if status == STATUS_MET else max(0, required - have),
            'achievement': round(achievement, 4),
            'contribution': round(contribution, 4),
        })

    total = len(requirements)
    if weighted_total > 0:
        score = int(round(100 * weighted_earned / weighted_total))
    else:
        # No requirements defined: there is nothing to be compatible with.
        score = 100

    missing_names = [d['skill_name'] for d in details if d['status'] == STATUS_MISSING]
    deficient_names = [
        f"{d['skill_name']} (needs {d['required_label']}, has {d['have_label']})"
        for d in details if d['status'] == STATUS_DEFICIENT
    ]

    if not total:
        explanation = 'This project has no required skills defined yet.'
    else:
        parts = [f'{met} of {total} requirement(s) met']
        if missing_names:
            parts.append('missing: ' + ', '.join(missing_names))
        if deficient_names:
            parts.append('below the required level: ' + ', '.join(deficient_names))
        if not missing_names and not deficient_names:
            parts.append('all required proficiencies covered')
        explanation = '; '.join(parts) + '.'

    return {
        'student_id': student.student_id,
        'student_number': student.student_number,
        'name': f'{student.last_name}, {student.first_name}',
        'full_name': f'{student.first_name} {student.last_name}',
        'course': student.course,
        'section': student.section,
        'year_level': student.year_level,
        'score': score,
        'total': total,
        'met_count': met,
        'deficient_count': deficient,
        'missing_count': missing,
        'details': details,
        'missing_skills': missing_names,
        'deficient_skills': deficient_names,
        'met_skills': [
            d['skill_name'] for d in details if d['status'] == STATUS_MET
        ],
        'explanation': explanation,
    }


def match_students_to_project(project, students=None):
    """Score every student against ``project`` and return them best-first.

    Ordering is fully deterministic: score desc, then surname, then student id.
    """
    requirements = project_requirements(project)
    if students is None:
        from .models import Student
        students = list(Student.objects.all())

    students = list(students)
    index = skill_index_for_students(students)
    results = [
        match_student_to_requirements(
            student, index.get(student.student_id, {}), requirements
        )
        for student in students
    ]
    results.sort(key=lambda r: (-r['score'], r['name'], r['student_id']))
    return results


def analyze_group_skills(group):
    """Skill-gap analysis of a group roster against its project requirements.

    For every required skill the **best** proficiency among the current members
    is compared with the required level:

    * ``satisfied``  best >= required
    * ``deficient``  0 < best < required (the ``gap`` is how many levels away)
    * ``missing``    nobody in the group recorded that skill

    ``match_percentage`` is the share of requirements that are satisfied.
    ``weighted_pct`` additionally credits partial proficiency
    (``sum(L * min(best / L, 1)) / sum(L)``), which is what the formation
    algorithm optimises.
    """
    required_skills = list(
        ProjectRequiredSkill.objects.filter(project_id=group.project_id)
        .select_related('skill')
        .order_by('skill__skill_name')
    )
    memberships = list(
        GroupMember.objects.filter(group_id=group.group_id)
        .select_related('student')
        .order_by('student__last_name', 'student__first_name', 'student_id')
    )
    member_students = [m.student for m in memberships]

    skill_map = {}
    if member_students:
        for record in StudentSkill.objects.filter(
            student__in=member_students
        ).select_related('student', 'skill'):
            skill_map.setdefault(record.skill_id, []).append(record)

    details = []
    satisfied_count = deficient_count = missing_count = 0
    weighted_earned = weighted_total = 0.0

    for req in required_skills:
        assigned = skill_map.get(req.skill_id, [])
        if assigned:
            best = max(assigned, key=lambda a: a.proficiency_level)
            best_level = best.proficiency_level
            covering_student = (
                f'{best.student.first_name} {best.student.last_name}'
            )
            if best_level >= req.required_level:
                status = 'satisfied'
                gap = 0
                satisfied_count += 1
            else:
                status = 'deficient'
                gap = req.required_level - best_level
                deficient_count += 1
        else:
            best_level = 0
            covering_student = None
            status = 'missing'
            gap = req.required_level
            missing_count += 1

        weighted_total += req.required_level
        weighted_earned += min(best_level, req.required_level)

        details.append({
            'skill_id': req.skill_id,
            'skill_name': req.skill.skill_name,
            'required_level': req.required_level,
            'required_label': proficiency_label(req.required_level),
            'best_level': best_level,
            'best_label': (
                proficiency_label(best_level) if best_level else 'Not recorded'
            ),
            'covering_student': covering_student,
            'status': status,
            'gap': gap,
        })

    total_required = len(required_skills)
    if total_required > 0:
        match_percentage = round((satisfied_count / total_required) * 100)
        weighted_pct = int(round(100 * weighted_earned / weighted_total))
    else:
        match_percentage = 100 if member_students else 0
        weighted_pct = match_percentage

    return {
        'total_required': total_required,
        'satisfied_count': satisfied_count,
        'deficient_count': deficient_count,
        'missing_count': missing_count,
        'gap_count': deficient_count + missing_count,
        'match_percentage': match_percentage,
        'weighted_pct': weighted_pct,
        'details': details,
        'members': [
            {
                'member_id': m.group_member_id,
                'student_id': m.student_id,
                'student_number': m.student.student_number,
                'name': f'{m.student.last_name}, {m.student.first_name}',
                'course': m.student.course,
                'section': m.student.section,
            }
            for m in memberships
        ],
    }


def recommend_candidates(group, limit=10):
    """Rank unassigned students by how much they would close this group's gaps.

    Scoring (all derived from the data, no magic numbers):

    1. Current requirement ``d`` has deficit ``deficit_d =
       max(0, L_d - best_d)`` where ``best_d`` is the best member level.
    2. A candidate contributes ``contribution_d = min(p_d, L_d)`` towards it,
       i.e. the candidate's usable proficiency capped at the requirement.
    3. ``gap_score = 100 * sum(L_d * contribution_d / L_d over deficits) /
       sum(L_d over deficits)`` is the share of the outstanding weighted gap
       the candidate would fill.
    4. Ties break on how many requirements the candidate fully satisfies, then
       on the total level they bring, then on name.

    Students already assigned to **any** group of this project are excluded and
    the group's remaining capacity is respected.
    """
    from .models import Student

    project = group.project
    requirements = project_requirements(project)
    if not requirements:
        return []

    required_skill_ids = [r['skill_id'] for r in requirements]

    assigned_ids = set(
        GroupMember.objects.filter(group__project=project)
        .values_list('student_id', flat=True)
    )
    candidates = list(
        Student.objects.exclude(student_id__in=assigned_ids)
        .order_by('last_name', 'first_name', 'student_id')
    )
    if not candidates:
        return []

    index = skill_index_for_students(candidates)

    # Current best proficiency per requirement inside the group.
    member_ids = list(
        group.members.values_list('student_id', flat=True)
    )
    best_in_group = {skill_id: 0 for skill_id in required_skill_ids}
    if member_ids:
        for record in StudentSkill.objects.filter(
            student_id__in=member_ids, skill_id__in=required_skill_ids
        ):
            if record.proficiency_level > best_in_group[record.skill_id]:
                best_in_group[record.skill_id] = record.proficiency_level

    deficits = {
        r['skill_id']: max(0, r['required_level'] - best_in_group[r['skill_id']])
        for r in requirements
    }
    total_deficit = sum(deficits.values())

    recommendations = []
    for student in candidates:
        levels = index.get(student.student_id, {})
        reasons = []
        closes = 0
        filled = 0.0
        brought = 0
        met_count = 0
        details = []

        for req in requirements:
            skill_id = req['skill_id']
            required = req['required_level']
            have = levels.get(skill_id, 0)
            deficit = deficits[skill_id]
            status = _status_for(have, required)
            if status == STATUS_MET:
                met_count += 1
            contribution = min(have, required)
            if deficit > 0:
                filled += min(have, deficit)
                if have >= required:
                    closes += 1
                    reasons.append(
                        f'Brings {proficiency_label(have)} {req["skill_name"]} '
                        f'({have}) - covers the required level {required}.'
                    )
                elif have > 0:
                    reasons.append(
                        f'Adds {proficiency_label(have)} {req["skill_name"]} '
                        f'({have}) - narrows the gap from {deficit} to '
                        f'{max(0, deficit - have)}.'
                    )
            brought += have
            details.append({
                'skill_name': req['skill_name'],
                'required_level': required,
                'have': have,
                'status': status,
                'deficit': deficit,
            })

        gap_score = (
            int(round(100 * filled / total_deficit)) if total_deficit else 100
        )

        recommendations.append({
            'student_id': student.student_id,
            'student_number': student.student_number,
            'name': f'{student.last_name}, {student.first_name}',
            'course': student.course,
            'section': student.section,
            'year_level': student.year_level,
            # Kept for the existing UI: share of the project's requirements the
            # candidate satisfies on their own.
            'coverage_pct': int(
                round(100 * met_count / len(requirements))
            ) if requirements else 100,
            'covered_count': met_count,
            'total_required': len(requirements),
            'met': [
                {
                    'skill_name': d['skill_name'],
                    'required': d['required_level'],
                    'have': d['have'],
                }
                for d in details if d['status'] == STATUS_MET
            ],
            'missing': [
                {
                    'skill_name': d['skill_name'],
                    'required': d['required_level'],
                    'have': d['have'],
                }
                for d in details if d['status'] != STATUS_MET
            ],
            # Kept for the existing UI ordering: weighted proficiency brought.
            'score': brought,
            'gap_score': gap_score,
            'closes_count': closes,
            'reasons': reasons[:4] or [
                'No outstanding requirement this student can improve; they '
                'would still add depth to the roster.'
            ],
            'details': details,
        })

    recommendations.sort(
        key=lambda r: (
            -r['gap_score'], -r['closes_count'], -r['score'], r['name'], r['student_id']
        )
    )
    return recommendations[:limit]

from django.urls import path
from . import views

app_name = 'students'

urlpatterns = [
    path('', views.student_list_page, name='student_list'),
    path('ajax/list/', views.student_list_ajax, name='student_list_ajax'),
    path('ajax/get/<int:pk>/', views.student_get_ajax, name='student_get_ajax'),
    path('ajax/save/', views.student_save_ajax, name='student_save_ajax'),
    path('ajax/delete/<int:pk>/', views.student_delete_ajax, name='student_delete_ajax'),

    path('skills/', views.skill_list_page, name='skill_list'),
    path('skills/ajax/list/', views.skill_list_ajax, name='skill_list_ajax'),
    path('skills/ajax/get/<int:pk>/', views.skill_get_ajax, name='skill_get_ajax'),
    path('skills/ajax/save/', views.skill_save_ajax, name='skill_save_ajax'),
    path('skills/ajax/delete/<int:pk>/', views.skill_delete_ajax, name='skill_delete_ajax'),

    path('student-skills/', views.student_skill_list_page, name='student_skill_list'),
    path('student-skills/ajax/list/', views.student_skill_list_ajax, name='student_skill_list_ajax'),
    path('student-skills/ajax/get/<int:pk>/', views.student_skill_get_ajax, name='student_skill_get_ajax'),
    path('student-skills/ajax/save/', views.student_skill_save_ajax, name='student_skill_save_ajax'),
    path('student-skills/ajax/delete/<int:pk>/', views.student_skill_delete_ajax, name='student_skill_delete_ajax'),

    path('projects/', views.project_list_page, name='project_list'),
    path('projects/ajax/list/', views.project_list_ajax, name='project_list_ajax'),
    path('projects/ajax/get/<int:pk>/', views.project_get_ajax, name='project_get_ajax'),
    path('projects/ajax/save/', views.project_save_ajax, name='project_save_ajax'),
    path('projects/ajax/delete/<int:pk>/', views.project_delete_ajax, name='project_delete_ajax'),

    path('project-skills/', views.project_skill_list_page, name='project_skill_list'),
    path('project-skills/ajax/list/', views.project_skill_list_ajax, name='project_skill_list_ajax'),
    path('project-skills/ajax/get/<int:pk>/', views.project_skill_get_ajax, name='project_skill_get_ajax'),
    path('project-skills/ajax/save/', views.project_skill_save_ajax, name='project_skill_save_ajax'),
    path('project-skills/ajax/delete/<int:pk>/', views.project_skill_delete_ajax, name='project_skill_delete_ajax'),

    path('groups/', views.group_list_page, name='group_list'),
    path('groups/ajax/list/', views.group_list_ajax, name='group_list_ajax'),
    path('groups/ajax/get/<int:pk>/', views.group_get_ajax, name='group_get_ajax'),
    path('groups/ajax/save/', views.group_save_ajax, name='group_save_ajax'),
    path('groups/ajax/delete/<int:pk>/', views.group_delete_ajax, name='group_delete_ajax'),
    path('groups/ajax/<int:group_pk>/unassigned-students/', views.group_unassigned_students_ajax, name='group_unassigned_students_ajax'),
    path('groups/ajax/<int:group_pk>/members/add/', views.group_member_add_ajax, name='group_member_add_ajax'),
    path('groups/ajax/<int:group_pk>/members/remove/<int:member_pk>/', views.group_member_remove_ajax, name='group_member_remove_ajax'),
    path('groups/ajax/<int:group_pk>/recommendations/', views.group_recommendations_ajax, name='group_recommendations_ajax'),
]

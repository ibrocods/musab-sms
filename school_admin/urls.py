from django.urls import path

from . import grant_views, setup_views, views

app_name = 'school_admin'

urlpatterns = [
    # Staff
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_create, name='staff_create'),
    path('staff/created/', views.staff_created, name='staff_created'),
    path('staff/<int:user_pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:user_pk>/deactivate/', views.staff_deactivate, name='staff_deactivate'),
    path('staff/<int:user_pk>/reactivate/', views.staff_reactivate, name='staff_reactivate'),
    path('staff/<int:user_pk>/reset-password/', views.staff_reset, name='staff_reset'),
    path('password/', views.change_password, name='change_password'),

    # Temporary access
    path('grants/', grant_views.grant_list, name='grant_list'),
    path('grants/give/', grant_views.grant_create, name='grant_create'),
    path('grants/<int:pk>/end/', grant_views.grant_revoke, name='grant_revoke'),

    # Subjects and classes
    path('setup/', setup_views.setup_home, name='setup_home'),
    path('setup/subjects/', setup_views.subject_list, name='subject_list'),
    path('setup/subjects/add/', setup_views.subject_create, name='subject_create'),
    path('setup/subjects/<int:pk>/edit/', setup_views.subject_edit, name='subject_edit'),
    path('setup/subjects/<int:pk>/toggle/', setup_views.subject_toggle, name='subject_toggle'),
    path('setup/classes/', setup_views.class_list, name='class_list'),
    path('setup/classes/add/', setup_views.class_create, name='class_create'),
    path('setup/classes/<int:pk>/', setup_views.class_detail, name='class_detail'),
    path('setup/classes/<int:pk>/edit/', setup_views.class_edit, name='class_edit'),
    path('setup/classes/<int:pk>/toggle/', setup_views.class_toggle, name='class_toggle'),
    path('setup/classes/<int:pk>/subjects/add/', setup_views.class_subject_add, name='class_subject_add'),
    path('setup/class-subjects/<int:pk>/remove/', setup_views.class_subject_remove, name='class_subject_remove'),
]
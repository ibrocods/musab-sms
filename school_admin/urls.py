from django.urls import path

from . import views

app_name = 'school_admin'

urlpatterns = [
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_create, name='staff_create'),
    path('staff/created/', views.staff_created, name='staff_created'),
    path('staff/<int:user_pk>/edit/', views.staff_edit, name='staff_edit'),
    path('staff/<int:user_pk>/deactivate/', views.staff_deactivate, name='staff_deactivate'),
    path('staff/<int:user_pk>/reactivate/', views.staff_reactivate, name='staff_reactivate'),
    path('staff/<int:user_pk>/reset-password/', views.staff_reset, name='staff_reset'),
    path('password/', views.change_password, name='change_password'),
]
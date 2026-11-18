from django.urls import path

from . import views

app_name = 'school_admin'

urlpatterns = [
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/add/', views.staff_create, name='staff_create'),
    path('staff/created/', views.staff_created, name='staff_created'),
]
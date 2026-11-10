"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.admin import views
from core import views, score_views, attendance_views
from django.urls import path
from django.contrib.auth import views as auth_views
from core import student_views
urlpatterns = [
    path('admin/', admin.site.urls),
     path('', views.home, name='home'),
     path('school.css', views.school_css, name='school_css'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('students/', student_views.student_list, name='student_list'),
    path('students/add/', student_views.student_create, name='student_create'),
    path('students/<int:pk>/archive/', student_views.student_archive, name='student_archive'),
    path('scores/', score_views.score_index, name='score_index'),
    path('scores/<int:class_subject_pk>/<int:assessment_pk>/', score_views.score_entry, name='score_entry'),
    path('scores/<int:class_subject_pk>/term/<int:term_pk>/lock/', score_views.result_lock, name='result_lock'),
    path('attendance/', attendance_views.attendance_index, name='attendance_index'),
path('attendance/<int:class_pk>/', attendance_views.attendance_register, name='attendance_register'),
]

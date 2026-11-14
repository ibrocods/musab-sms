from django.urls import path

from . import views

app_name = 'report_cards'

urlpatterns = [
    path('', views.report_card_index, name='index'),
    path('student/<int:student_pk>/', views.report_card_view, name='card'),
    path('student/<int:student_pk>/comment/', views.report_card_comment, name='comment'),
    path('student/<int:student_pk>/approve/', views.report_card_approve, name='approve'),
    path('student/<int:student_pk>/reopen/', views.report_card_reopen, name='reopen'),
    path('student/<int:student_pk>/print/', views.report_card_print, name='print'),
]
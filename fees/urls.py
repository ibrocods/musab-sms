from django.urls import path

from . import views

app_name = 'fees'

urlpatterns = [
    path('', views.index, name='index'),
    path('debtors/', views.debtors_list, name='debtors'),
    path('setup/', views.setup, name='setup'),
    path('setup/add/', views.fee_create, name='fee_create'),
    path('setup/<int:pk>/toggle/', views.fee_toggle, name='fee_toggle'),
    path('student/<int:student_pk>/', views.statement, name='statement'),
    path('student/<int:student_pk>/payments/', views.payment_record, name='payment_record'),
    path('student/<int:student_pk>/discounts/', views.discount_grant, name='discount_grant'),
    path('payments/<int:pk>/reverse/', views.payment_reverse, name='payment_reverse'),
    path('discounts/<int:pk>/end/', views.discount_end, name='discount_end'),
]
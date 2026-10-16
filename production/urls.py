from django.urls import path

from . import views

app_name = "production"

urlpatterns = [
    path("", views.work_order_list, name="list"),
    path("new/", views.work_order_create, name="create"),
    path("<int:pk>/", views.work_order_detail, name="detail"),
    path("<int:pk>/operations/<int:op_pk>/start/", views.operation_start, name="operation_start"),
    path("<int:pk>/operations/<int:op_pk>/complete/", views.operation_complete, name="operation_complete"),
]
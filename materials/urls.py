from django.urls import path

from . import views

app_name = "materials"

urlpatterns = [
    path("", views.intake_list, name="list"),
    path("new/", views.intake_create, name="create"),
    path("<int:pk>/", views.intake_detail, name="detail"),
    path("<int:pk>/clear/", views.intake_clear, name="clear"),
    path("<int:pk>/reject/", views.intake_reject, name="reject"),
]
from django.urls import path

from . import views

app_name = "quality"

urlpatterns = [
    path("", views.template_list, name="template_list"),
    path("new/", views.template_create, name="template_create"),
    path("<int:pk>/", views.template_detail, name="template_detail"),
    path("<int:pk>/fields/add/", views.field_add, name="field_add"),
    path("<int:pk>/fields/<int:field_pk>/remove/", views.field_remove, name="field_remove"),
    path("<int:pk>/submit/", views.template_submit, name="template_submit"),
    path("<int:pk>/approve/", views.template_approve, name="template_approve"),
    path("<int:pk>/reject/", views.template_reject, name="template_reject"),
]
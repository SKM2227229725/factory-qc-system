from django.urls import path

from . import inspection_views as views

app_name = "inspections"

urlpatterns = [
    path("", views.inspection_list, name="list"),
    path("start/", views.inspection_start, name="start"),
    path("<int:pk>/", views.inspection_detail, name="detail"),
    path("<int:pk>/fields/<int:field_pk>/reading/", views.reading_add, name="reading_add"),
    path("<int:pk>/readings/<int:reading_pk>/photos/", views.photo_add, name="photo_add"),
    path("<int:pk>/submit/", views.inspection_submit, name="submit"),
]
from django.urls import path

from . import inspection_views as views
from . import review_views

app_name = "inspections"

urlpatterns = [
    path("", views.inspection_list, name="list"),
    path("start/", views.inspection_start, name="start"),
    path("<int:pk>/", views.inspection_detail, name="detail"),
    path("<int:pk>/fields/<int:field_pk>/reading/", views.reading_add, name="reading_add"),
    path("<int:pk>/readings/<int:reading_pk>/photos/", views.photo_add, name="photo_add"),
    path("<int:pk>/submit/", views.inspection_submit, name="submit"),
    
    # Review & MRB
    path("review/", review_views.review_queue, name="review_queue"),
    path("mrb/", review_views.mrb_queue, name="mrb_queue"),
    path("<int:pk>/approve/", review_views.inspection_approve, name="approve"),
    path("<int:pk>/concede/", review_views.inspection_concede, name="concede"),
    path("<int:pk>/reject/", review_views.inspection_reject, name="reject"),
    path("<int:pk>/disposition/", review_views.disposition_create, name="disposition"),
]
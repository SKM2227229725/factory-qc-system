from django.urls import path
from . import views

app_name = "dispatch"

urlpatterns = [
    path("", views.dispatch_board, name="board"),
    path("<int:pk>/issue/", views.dispatch_create, name="create"),
    path("<int:pk>/gate-pass/", views.gate_pass, name="gate_pass"),
    path("<int:pk>/packing-slip/", views.packing_slip, name="packing_slip"),
]
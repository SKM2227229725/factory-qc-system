from django.contrib import admin
from django.urls import include, path
from django.shortcuts import render


def home_view(request):
    from materials.models import RawMaterialIntake
    qs = RawMaterialIntake.objects.all()
    ctx = {
        "total_intakes": qs.count(),
        "cleared_intakes": qs.filter(status="CLEARED").count(),
        "quarantined_intakes": qs.filter(status="QUARANTINED").count(),
        "in_lab_intakes": qs.filter(status="IN_LAB").count(),
        "received_intakes": qs.filter(status="RECEIVED").count(),
        "recent_intakes": qs.order_by("-received_at")[:5],
    }
    return render(request, "home.html", ctx)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", home_view, name="home"),
    path("intake/", include("materials.urls")),
    path("pdi/", include("quality.urls")),
]
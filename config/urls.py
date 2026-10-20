from django.contrib import admin
from django.urls import path

from core.views import salud

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/salud/", salud),
]
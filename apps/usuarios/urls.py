from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [path("mi-perfil/", views.mi_perfil, name="mi_perfil")]

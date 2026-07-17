from django.urls import path

from . import views

app_name = "trabajo_social"

urlpatterns = [
    path("ficha/<int:expediente_id>/", views.ficha, name="ficha"),
]

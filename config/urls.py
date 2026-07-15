"""URLs raíz de SIBU."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="inicio.html"), name="inicio"),
    path("cuentas/", include("django.contrib.auth.urls")),  # login/logout/password
    # API v1
    path("api/v1/", include("api.v1.urls")),
    path("academico/", include("apps.academico.urls")),
    path("expediente/", include("apps.expediente.urls")),
    path("citas/", include("apps.citas.urls")),
    path("enfermeria/", include("apps.enfermeria.urls")),
    path("medicina/", include("apps.medicina.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar
        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass

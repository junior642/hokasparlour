from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from .sitemaps import StaticViewSitemap, ProductSitemap
from parlour.views import robots_txt
from django.http import FileResponse, HttpResponse
from two_factor.urls import urlpatterns as tf_urls
from two_factor.admin import AdminSiteOTPRequired
import os


# ── Secure Admin: requires 2FA + 30 min session timeout ──────────────────────
class SecureAdminSite(AdminSiteOTPRequired):
    def each_context(self, request):
        context = super().each_context(request)
        # Force 2hrs-minute session timeout for admin users
        request.session.set_expiry(3600)
        return context

admin.site.__class__ = SecureAdminSite
# ─────────────────────────────────────────────────────────────────────────────


sitemaps = {
    'static': StaticViewSitemap,
    'products': ProductSitemap,
}


def google_verify(request):
    file_path = os.path.join(settings.BASE_DIR, 'static', 'googleb193ab12b0274614.html')
    return FileResponse(open(file_path, 'rb'), content_type='text/html')


urlpatterns = [
    path('accounts/', include('allauth.urls')),
    path('hoka-secure-panel-2024/', admin.site.urls),
    path('whatsapp/', include('whatsapphoka.urls')),
    path('', include(tf_urls)),
    path('', include('parlour.urls')),
    path('admin-dashboard/', include('hokaadmin.urls')),
    path('finance/', include('finance.urls', namespace='finance')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', robots_txt),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
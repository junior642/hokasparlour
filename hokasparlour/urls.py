from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from .sitemaps import StaticViewSitemap, ProductSitemap
from parlour.views import robots_txt
from django.http import FileResponse
import os

sitemaps = {
    'static': StaticViewSitemap,
    'products': ProductSitemap,
}

# Add this at the top with your other imports
def google_verification(request):
    return HttpResponse(
        'google-site-verification: googleb193ab12b0274614.html',
        content_type='text/plain'
    )


urlpatterns = [
  path('googleb193ab12b0274614.html', google_verification),

    path('admin/', admin.site.urls),
    path('', include('parlour.urls')),
    path('admin-dashboard/', include('hokaadmin.urls')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', robots_txt),
    path('googleb193ab12b0274614.html', google_verify),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

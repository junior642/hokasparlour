from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from .sitemaps import StaticViewSitemap, ProductSitemap
from parlour.views import robots_txt
from django.http import FileResponse, HttpResponse
import os

sitemaps = {
    'static': StaticViewSitemap,
    'products': ProductSitemap,
}

def google_verify(request):
    file_path = os.path.join(settings.BASE_DIR, 'static', 'googleb193ab12b0274614.html')
    return FileResponse(open(file_path, 'rb'), content_type='text/html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('parlour.urls')),
    path('admin-dashboard/', include('hokaadmin.urls')),
    path('finance/', include('finance.urls', namespace='finance')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path('robots.txt', robots_txt),
    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'
    
    def items(self):
        # List all your main page URL names here
        return ['home', 'login', 'signup', 'about', 'contact', 'order_tracking']
    
    def location(self, item):
        return reverse(item)

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from parlour.models import Product


class StaticViewSitemap(Sitemap):
    protocol = 'https'

    def items(self):
        return [
            ('home',    0.9, 'daily'),
            ('about',   0.7, 'monthly'),
            ('contact', 0.6, 'monthly'),
            ('terms',   0.3, 'yearly'),
            ('privacy', 0.3, 'yearly'),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class ProductSitemap(Sitemap):
    protocol = 'https'
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Product.objects.all()

    def location(self, obj):
        return reverse('product_detail', args=[obj.id])

    def lastmod(self, obj):
        return getattr(obj, 'updated_at', None) or getattr(obj, 'created_at', None)

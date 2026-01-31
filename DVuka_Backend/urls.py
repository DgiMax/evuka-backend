from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from DVuka_Backend.views import unified_search_api
from events.views import BestUpcomingEventView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("users/", include("users.urls")),
    path('api/v1/search/', unified_search_api, name='unified_search'),
    path("organizations/", include("organizations.urls")),
    path("", include("courses.urls")),
    path("events/", include("events.urls")),
    path("marketplace/", include("marketplace.urls")),
    path("orders/", include("orders.urls")),
    path("payments/", include("payments.urls")),
    path('announcements/', include('announcements.urls')),
    path('revenue/', include('revenue.urls')),
    path('students/', include("students.urls")),
    path('live/', include("live.urls")),
    path('community/', include('org_community.urls')),
    path("ai/", include("ai_assistant.urls")),
    path('notifications/', include('notifications.urls')),
    path('help_center/', include('help_center.urls')),
    path('books/', include('books.urls')),
    path('core/', include('core.urls')),
    path(
        'best-upcoming-events/',
        BestUpcomingEventView.as_view(),
        name='best-upcoming'
    ),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# your_project/views.py

from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from courses.models import Course
from events.models import Event
from organizations.models import Organization
# Import the utility function
from users.utils.search_utils import sqlite_search_model


def unified_search_api(request):
    """
    Handles unified search across Courses, Events, and Organizations.
    Uses SQLite-compatible manual scoring.
    """
    query = request.GET.get('q', '').strip()
    results = {
        'courses': [],
        'events': [],
        'organizations': []
    }

    if not query or len(query) < 3:  # Require a minimum of 3 characters for performance
        return JsonResponse(results)

    # --- A. Course Search ---
    # Public Filter: Must be published
    course_filter = Q(status='published')
    results['courses'] = sqlite_search_model(
        model_class=Course,
        query=query,
        public_filter=course_filter,
        title_field='title',
        slug_field='slug',
        description_field='short_description',
        limit=5
    )

    # --- B. Event Search ---
    # Public Filter: Must be approved/scheduled AND be upcoming
    event_filter = Q(event_status__in=['approved', 'scheduled']) & Q(start_time__gte=timezone.now())
    results['events'] = sqlite_search_model(
        model_class=Event,
        query=query,
        public_filter=event_filter,
        title_field='title',
        slug_field='slug',
        description_field='overview',
        limit=5
    )

    # --- C. Organization Search ---
    # Public Filter: Must be approved
    org_filter = Q(approved=True)
    results['organizations'] = sqlite_search_model(
        model_class=Organization,
        query=query,
        public_filter=org_filter,
        title_field='name',
        slug_field='slug',
        description_field='description',
        limit=3
    )

    return JsonResponse(results)
from django.db.models import Q, F
from django.utils import timezone
from courses.models import Course, Enrollment
from events.models import Event, EventRegistration
from organizations.models import Organization, OrgMembership
from books.models import Book, BookAccess


class UnifiedSearchService:
    def __init__(self, user, query):
        self.user = user
        self.query = query
        self.limit = 5

    def get_results(self):
        return {
            'courses': self._search_courses(),
            'events': self._search_events(),
            'organizations': self._search_organizations(),
            'books': self._search_books(),
        }

    def _format_result(self, instance, title_field, thumb_field=None):
        """Helper to standardize results for the frontend Navbar"""
        return {
            'id': instance.id,
            'title': getattr(instance, title_field),
            'slug': instance.slug,
            'thumbnail': getattr(instance, thumb_field).url if thumb_field and getattr(instance, thumb_field) else None,
            'type': instance.__class__.__name__.lower(),
        }

    def _search_organizations(self):
        qs = Organization.objects.filter(approved=True, name__icontains=self.query)

        if self.user.is_authenticated:
            member_org_ids = OrgMembership.objects.filter(user=self.user).values_list('organization_id', flat=True)
            qs = qs.exclude(id__in=member_org_ids)

        return [self._format_result(obj, 'name', 'logo') for obj in qs[:3]]

    def _search_courses(self):
        qs = Course.objects.filter(
            status='published',
            is_public=True
        ).filter(
            Q(title__icontains=self.query) | Q(short_description__icontains=self.query)
        )

        if self.user.is_authenticated:
            enrolled_course_ids = Enrollment.objects.filter(user=self.user).values_list('course_id', flat=True)
            qs = qs.exclude(id__in=enrolled_course_ids)

        return [self._format_result(obj, 'title', 'thumbnail') for obj in qs[:self.limit]]

    def _search_events(self):
        qs = Event.objects.filter(
            event_status__in=['approved', 'scheduled'],
            start_time__gte=timezone.now(),
            who_can_join='anyone'
        ).filter(
            Q(title__icontains=self.query) | Q(overview__icontains=self.query)
        )

        if self.user.is_authenticated:
            registered_event_ids = EventRegistration.objects.filter(
                user=self.user,
                status='registered'
            ).values_list('event_id', flat=True)
            qs = qs.exclude(id__in=registered_event_ids)

        return [self._format_result(obj, 'title', 'banner_image') for obj in qs[:self.limit]]

    def _search_books(self):
        qs = Book.objects.filter(status='published', title__icontains=self.query)

        if self.user.is_authenticated:
            owned_book_ids = BookAccess.objects.filter(user=self.user).values_list('book_id', flat=True)
            qs = qs.exclude(id__in=owned_book_ids)

        return [self._format_result(obj, 'title', 'cover_image') for obj in qs[:self.limit]]
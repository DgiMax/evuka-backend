from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer
from .utils import push_unread_count_update


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Unified Inbox.
    - Context: Org A -> Shows Org A notifications.
    - Context: Global -> Shows Personal/Marketplace notifications.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = Notification.objects.filter(recipient=user)

        active_org = getattr(self.request, "active_organization", None)

        if active_org:
            qs = qs.filter(organization=active_org)
        else:
            qs = qs.filter(organization__isnull=True)

        return qs.select_related(
            'content_type',
            'organization'
        ).prefetch_related(
            'content_object'
        ).order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()

        try:
            push_unread_count_update(request.user)
        except Exception as e:
            pass

        return Response({'status': 'marked as read'})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        user = self.request.user

        queryset = self.get_queryset().filter(is_read=False)

        updated_count = queryset.update(is_read=True, read_at=timezone.now())

        if updated_count > 0:
            push_unread_count_update(user)

        return Response({'status': f'Marked {updated_count} notifications as read'})

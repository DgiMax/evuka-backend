from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets, mixins, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model

from notifications.models import Notification
from notifications.utils import push_unread_count_update

from .models import Announcement
from .serializers import (
    TutorAnnouncementSerializer,
    StudentAnnouncementSerializer,
    TargetCourseSerializer
)
from .permissions import IsActiveOrgAdminOrOwner
from organizations.models import OrgMembership
from courses.models import Course, Enrollment


def _create_notifications_for_announcement(announcement: Announcement):
    """
    Finds all target students for a published announcement and creates
    generic Notification objects for them.
    """

    courses_qs = Course.objects.none()
    audience = announcement.audience_type
    creator = announcement.creator
    organization = announcement.organization

    if audience == 'all_personal_courses' and not organization:
        courses_qs = Course.objects.filter(creator=creator, organization__isnull=True)
    elif audience == 'my_org_courses' and organization:
        courses_qs = Course.objects.filter(creator=creator, organization=organization)
    elif audience == 'all_org_courses' and organization:
        courses_qs = Course.objects.filter(organization=organization)
    elif audience == 'specific_courses':
        courses_qs = announcement.courses.all()

    student_ids = set(Enrollment.objects.filter(
        course__in=courses_qs,
        status='active',
        role='student'
    ).values_list('user_id', flat=True).distinct())

    if not student_ids:
        return

    announcement_type = ContentType.objects.get_for_model(announcement)

    existing_recipient_ids = set(Notification.objects.filter(
        content_type=announcement_type,
        object_id=announcement.id,
        recipient_id__in=student_ids
    ).values_list('recipient_id', flat=True))

    ids_to_notify = student_ids - existing_recipient_ids

    notifications_to_create = []

    for uid in ids_to_notify:
        notifications_to_create.append(
            Notification(
                recipient_id=uid,
                content_type=announcement_type,
                object_id=announcement.id,
                notification_type='announcement',
                verb=f"New Announcement: {announcement.title[:100]}...",
                organization=organization,
                is_read=False
            )
        )

    if notifications_to_create:
        Notification.objects.bulk_create(notifications_to_create)

        User = get_user_model()

        users_to_push = User.objects.filter(pk__in=ids_to_notify)

        for user in users_to_push:
            try:
                push_unread_count_update(user)
            except Exception:
                pass


class TargetableCoursesListView(APIView):
    """
    A lightweight, read-only endpoint to get a list of courses
    a tutor can create announcements for. This is context-aware.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TargetCourseSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        active_org = getattr(request, "active_organization", None)

        queryset = Course.objects.none()

        if active_org:
            try:
                membership = OrgMembership.objects.get(user=user, organization=active_org)

                if membership.is_admin_or_owner():
                    queryset = Course.objects.filter(organization=active_org)
                elif membership.role == 'tutor':
                    queryset = Course.objects.filter(organization=active_org, creator=user)
                else:
                    pass

            except OrgMembership.DoesNotExist:
                pass

        else:
            queryset = Course.objects.filter(
                creator_profile__user=user,
                organization__isnull=True,
            )

        serializer = TargetCourseSerializer(queryset.order_by('title'), many=True)
        return Response(serializer.data)


class TutorAnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = TutorAnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        base_qs = Announcement.objects.select_related("creator", "organization")

        if active_org:
            try:
                membership = OrgMembership.objects.get(user=user, organization=active_org)
            except OrgMembership.DoesNotExist:
                return Announcement.objects.none()

            if membership.is_admin_or_owner():
                return base_qs.filter(organization=active_org)
            else:
                return base_qs.filter(organization=active_org, creator=user)
        else:
            return base_qs.filter(organization__isnull=True, creator=user)

    def perform_create(self, serializer):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)
        status = serializer.validated_data.get('status', 'draft')
        publish_at = serializer.validated_data.get('publish_at')

        published_at_time = None
        is_auto_approved = False
        if not active_org:
            is_auto_approved = True
        else:
            membership = OrgMembership.objects.get(user=user, organization=active_org)
            if membership.is_admin_or_owner():
                is_auto_approved = True

        if is_auto_approved:
            if status == 'published':
                published_at_time = timezone.now()
            elif status == 'scheduled' and not publish_at:
                serializer.validated_data['status'] = 'draft'
        else:
            if status in ['published', 'scheduled']:
                status = 'pending_approval'
                serializer.validated_data['status'] = status

        announcement = serializer.save(
            creator=user,
            organization=active_org,
            published_at=published_at_time
        )

        if announcement.status == 'published' and published_at_time:
            _create_notifications_for_announcement(announcement)

    def perform_update(self, serializer):
        user = self.request.user
        active_org = getattr(self.request, "active_organization", None)

        old_status = self.get_object().status
        new_status = serializer.validated_data.get('status', old_status)

        published_at_time = None

        is_auto_approved = False
        if not active_org:
            is_auto_approved = True
        else:
            membership = OrgMembership.objects.get(user=user, organization=active_org)
            if membership.is_admin_or_owner():
                is_auto_approved = True

        if new_status == 'published' and old_status != 'published':
            if is_auto_approved:
                published_at_time = timezone.now()
                serializer.save(published_at=published_at_time)
            else:
                serializer.validated_data['status'] = 'pending_approval'
                serializer.save()
        elif new_status == 'pending_approval' and is_auto_approved:
            serializer.validated_data['status'] = 'draft'
            serializer.save()
        else:
            serializer.save()

        if new_status == 'published' and old_status != 'published' and published_at_time:
            _create_notifications_for_announcement(self.get_object())

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[permissions.IsAuthenticated, IsActiveOrgAdminOrOwner],
        url_path="update-status",
    )
    def update_status(self, request, pk=None):
        announcement = self.get_object()
        new_status = request.data.get("status")

        if not new_status or new_status not in dict(Announcement.Status.choices):
            return Response(
                {"error": f"Invalid status '{new_status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_org = getattr(request, "active_organization", None)
        if not active_org or announcement.organization != active_org:
            return Response(
                {"error": "This announcement does not belong to your active organization."},
                status=status.HTTP_403_FORBIDDEN,
            )

        old_status = announcement.status

        if new_status == 'published' and old_status != 'published':
            announcement.status = 'published'
            announcement.published_at = timezone.now()
            announcement.approver = request.user
            announcement.save(update_fields=['status', 'published_at', 'approver'])

            _create_notifications_for_announcement(announcement)

        elif new_status == 'scheduled' and not announcement.publish_at:
            return Response(
                {"error": "Cannot set status to 'Scheduled' without a 'publish_at' date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            announcement.status = new_status
            announcement.save(update_fields=['status'])

        return Response(
            {"message": f"Announcement status updated to '{new_status}'."},
            status=status.HTTP_200_OK,
        )


class StudentAnnouncementViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet
):
    """
    View for students to browse Announcement HISTORY within specific contexts
    (e.g., inside a specific Course page or Organization Portal).

    NOTE: For the main 'Notification Feed', use NotificationViewSet.
    """
    serializer_class = StudentAnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _get_relevant_announcement_ids(self):
        user = self.request.user

        enrollments = Enrollment.objects.filter(user=user, status='active').select_related('course')
        my_course_ids = [e.course_id for e in enrollments]

        my_personal_creator_ids = set()
        my_org_ids = set()
        my_org_creator_ids = set()

        for e in enrollments:
            course = e.course
            if course.organization_id:
                my_org_ids.add(course.organization_id)
                my_org_creator_ids.add(course.creator_id)
            else:
                my_personal_creator_ids.add(course.creator_id)

        q_personal_all = Q(organization__isnull=True, audience_type='all_personal_courses',
                           creator_id__in=my_personal_creator_ids)
        q_personal_specific = Q(organization__isnull=True, audience_type='specific_courses',
                                courses__id__in=my_course_ids)

        q_org_all = Q(organization_id__in=my_org_ids, audience_type='all_org_courses')
        q_org_tutor_all = Q(organization_id__in=my_org_ids, audience_type='my_org_courses',
                            creator_id__in=my_org_creator_ids)
        q_org_specific = Q(organization_id__in=my_org_ids, audience_type='specific_courses',
                           courses__id__in=my_course_ids)

        final_q = (q_personal_all | q_personal_specific | q_org_all | q_org_tutor_all | q_org_specific)

        return Announcement.objects.filter(status='published').filter(final_q).values_list('id', flat=True).distinct()

    def get_queryset(self):
        relevant_announcement_ids = self._get_relevant_announcement_ids()
        base_qs = Announcement.objects.filter(pk__in=relevant_announcement_ids)

        active_org = getattr(self.request, "active_organization", None)

        if active_org:
            base_qs = base_qs.filter(organization=active_org)
        else:
            base_qs = base_qs.filter(organization__isnull=True)

        return base_qs.select_related('creator', 'organization').order_by('-published_at')

    @action(detail=False, methods=['get'], url_path='course/(?P<course_slug>[^/.]+)')
    def course_announcements(self, request, course_slug=None):
        """
        Get announcements strictly relevant to a specific course page.
        """
        if not course_slug:
            return Response({"error": "Course slug is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_course = Course.objects.get(slug=course_slug)
        except Course.DoesNotExist:
            return Response({"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

        relevant_ids = self._get_relevant_announcement_ids()

        q_specific = Q(courses__pk=target_course.pk)
        q_context = Q()

        if target_course.organization:
            q_context |= Q(organization=target_course.organization,
                           audience_type__in=['all_org_courses', 'my_org_courses'])
        else:
            q_context |= Q(organization__isnull=True, creator=target_course.creator,
                           audience_type='all_personal_courses')

        final_qs = Announcement.objects.filter(pk__in=relevant_ids).filter(q_specific | q_context).distinct().order_by(
            '-published_at')

        serializer = self.get_serializer(final_qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='mark-as-read')
    def mark_as_read(self, request, pk=None):
        """
        Marks the generic Notification linked to this Announcement as read.
        Useful when a user clicks an announcement inside a Course Board (not the Notification Feed).
        """
        user = request.user
        announcement = self.get_object()
        announcement_type = ContentType.objects.get_for_model(announcement)

        notification, created = Notification.objects.get_or_create(
            recipient=user,
            content_type=announcement_type,
            object_id=announcement.id,
            defaults={
                'verb': f"Read: {announcement.title[:50]}",
                'organization': announcement.organization,
                'notification_type': 'announcement',
                'is_read': True,
                'read_at': timezone.now()
            }
        )

        if not created and not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=['is_read', 'read_at'])

        push_unread_count_update(user)

        return Response({'status': 'marked as read'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """
        Returns the unread count based on the CURRENT CONTEXT.
        """
        user = request.user
        active_org = getattr(request, "active_organization", None)

        qs = Notification.objects.filter(recipient=user, is_read=False)

        if active_org:
            qs = qs.filter(organization=active_org)
        else:
            qs = qs.filter(organization__isnull=True)

        return Response({'unread_count': qs.count()})
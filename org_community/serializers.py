from rest_framework import serializers
from django.db.models import Count, Q
from .models import OrgJoinRequest, OrgInvitation
from organizations.models import Organization, OrgMembership
from organizations.serializers import OrgUserSerializer


class OrgBrandingSerializer(serializers.Serializer):
    """ Read-only serializer for nested branding JSON """
    logo_url = serializers.URLField(read_only=True)


class OrgDiscoverySerializer(serializers.ModelSerializer):
    """
    Serializer for the public organization discovery page.
    Includes stats and user-specific status (member, pending).
    """
    branding = OrgBrandingSerializer(read_only=True)
    stats = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    has_pending_request = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ('id', 'name', 'slug', 'description', 'branding', 'stats', 'is_member', 'has_pending_request')

    def get_stats(self, obj):
        tutors = OrgMembership.objects.filter(organization=obj, role__in=['owner', 'admin', 'tutor'],
                                              is_active=True).count()
        students = OrgMembership.objects.filter(organization=obj, role='student', is_active=True).count()
        return {"tutors": tutors, "students": students}

    def _get_user(self):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            return request.user
        return None

    def get_is_member(self, obj):
        """ Check if the current user is an active member. """
        user = self._get_user()
        if not user or not user.is_authenticated:
            return False
        return OrgMembership.objects.filter(organization=obj, user=user, is_active=True).exists()

    def get_has_pending_request(self, obj):
        """ Check if the user has a pending join request OR invitation. """
        user = self._get_user()
        if not user or not user.is_authenticated:
            return False

        has_request = OrgJoinRequest.objects.filter(organization=obj, user=user, status='pending').exists()
        if has_request:
            return True

        has_invitation = OrgInvitation.objects.filter(organization=obj, invited_user=user, status='pending').exists()
        return has_invitation


class OrgJoinRequestCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for a USER to create a new join request.
    Validates against existing memberships or requests.
    """
    organization = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Organization.objects.filter(approved=True)
    )

    class Meta:
        model = OrgJoinRequest
        fields = ['organization', 'message']

    def validate(self, attrs):
        user = self.context['request'].user
        org = attrs['organization']

        if OrgMembership.objects.filter(user=user, organization=org).exists():
            raise serializers.ValidationError("You are already a member of this organization.")

        if OrgJoinRequest.objects.filter(user=user, organization=org, status='pending').exists():
            raise serializers.ValidationError("You already have a pending request for this organization.")

        if OrgInvitation.objects.filter(invited_user=user, organization=org, status='pending').exists():
            raise serializers.ValidationError(
                "You have a pending invitation from this organization. Please check your invitations.")

        return attrs


class OrgJoinRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for ADMINS to view incoming join requests.
    Includes nested user details.
    """
    user = OrgUserSerializer(read_only=True)

    class Meta:
        model = OrgJoinRequest
        fields = ['id', 'user', 'message', 'status', 'created_at']


class OrgInvitationSerializer(serializers.ModelSerializer):
    """
    Serializer for USERS to view their pending invitations.
    Includes nested details of who invited them.
    """
    organization = serializers.ReadOnlyField(source='organization.name')
    invited_by = OrgUserSerializer(read_only=True)

    class Meta:
        model = OrgInvitation
        fields = ['id', 'organization', 'invited_by', 'role', 'status', 'created_at']


class UserJoinRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for USERS to view their *own* sent join requests.
    """
    organization = serializers.ReadOnlyField(source='organization.name')

    class Meta:
        model = OrgJoinRequest
        fields = ['id', 'organization', 'message', 'status', 'created_at']
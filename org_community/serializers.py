from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import AdvancedOrgInvitation, NegotiationLog, OrgJoinRequest
from organizations.models import Organization, OrgMembership
from organizations.serializers import OrgUserSerializer, OrganizationSimpleSerializer

User = get_user_model()


class OrgDiscoverySerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    has_pending_request = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ('id', 'name', 'slug', 'description', 'logo', 'branding', 'stats', 'is_member', 'has_pending_request')

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

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
        user = self._get_user()
        if not user or not user.is_authenticated:
            return False
        return OrgMembership.objects.filter(organization=obj, user=user, is_active=True).exists()

    def get_has_pending_request(self, obj):
        user = self._get_user()
        if not user or not user.is_authenticated:
            return False

        has_request = OrgJoinRequest.objects.filter(organization=obj, user=user, status='pending').exists()
        if has_request:
            return True

        has_invitation = AdvancedOrgInvitation.objects.filter(organization=obj, email=user.email).exclude(
            gov_status__in=['accepted', 'rejected', 'revoked'],
            tutor_status__in=['accepted', 'rejected', 'revoked']
        ).exists()
        return has_invitation


class OrgJoinRequestCreateSerializer(serializers.ModelSerializer):
    organization = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Organization.objects.filter(approved=True)
    )

    class Meta:
        model = OrgJoinRequest
        fields = ['organization', 'message', 'desired_role', 'proposed_commission']

    def validate(self, attrs):
        user = self.context['request'].user
        org = attrs['organization']
        role = attrs.get('desired_role', 'tutor')
        commission = attrs.get('proposed_commission', 0)

        if OrgMembership.objects.filter(user=user, organization=org).exists():
            raise serializers.ValidationError("You are already a member of this organization.")

        if OrgJoinRequest.objects.filter(user=user, organization=org, status='pending').exists():
            raise serializers.ValidationError("You already have a pending request for this organization.")

        if role == 'tutor':
            if commission < 40:
                raise serializers.ValidationError(
                    {"proposed_commission": "Minimum allowable commission request is 40%."})
            if commission > 100:
                raise serializers.ValidationError({"proposed_commission": "Commission cannot exceed 100%."})

        return attrs


class OrgJoinRequestSerializer(serializers.ModelSerializer):
    user = OrgUserSerializer(read_only=True)
    organization = OrganizationSimpleSerializer(read_only=True)

    class Meta:
        model = OrgJoinRequest
        fields = [
            'id', 'user', 'organization', 'message', 'status',
            'desired_role', 'proposed_commission', 'created_at'
        ]


class InviteActionSerializer(serializers.Serializer):
    section = serializers.ChoiceField(choices=['governance', 'teaching'])
    action = serializers.ChoiceField(choices=['accept', 'reject', 'counter'])
    counter_value = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data['action'] == 'counter' and data.get('counter_value') is None:
            raise serializers.ValidationError("Counter value required for counter action.")
        return data


class NegotiationLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.ReadOnlyField(source='actor.username')

    class Meta:
        model = NegotiationLog
        fields = ['id', 'actor', 'actor_name', 'action', 'previous_value', 'new_value', 'note', 'created_at']


class AdvancedInvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.ReadOnlyField(source='invited_by.username')
    logs = NegotiationLogSerializer(many=True, read_only=True)
    organization = OrganizationSimpleSerializer(read_only=True)

    class Meta:
        model = AdvancedOrgInvitation
        fields = [
            'id', 'organization', 'invited_by', 'invited_by_name',
            'email', 'gov_role', 'gov_status',
            'is_tutor_invite', 'tutor_commission', 'tutor_status',
            'created_at', 'updated_at', 'logs', 'is_fully_resolved'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'invited_by', 'organization', 'logs']

    def create(self, validated_data):
        if validated_data.get('is_tutor_invite'):
            comm = validated_data.get('tutor_commission', 0)
            if comm < 10:
                raise serializers.ValidationError({"tutor_commission": "Minimum commission is 10%."})
        return super().create(validated_data)
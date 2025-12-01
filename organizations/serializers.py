import json
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from courses.models import Course
from events.models import Event
from org_community.models import OrgJoinRequest, OrgInvitation
from users.models import CreatorProfile
from .models import Organization, OrgMembership, GuardianLink, OrgLevel, OrgCategory

User = get_user_model()

class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = "__all__"
        read_only_fields = ("slug", "approved", "created_at", "updated_at")


class OrgUserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField(source='get_full_name')
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'full_name')


class OrgMembershipSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_slug = serializers.CharField(source="organization.slug", read_only=True)
    user = OrgUserSerializer(read_only=True)
    class Meta:
        model = OrgMembership
        fields = ('id', 'user', 'organization', 'organization_name', 'organization_slug', 'role', 'is_active', 'date_joined')
        read_only_fields = ('date_joined', 'organization')


class OrgCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgCategory
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['organization', 'created_at']


class OrgLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgLevel
        fields = ['id', 'name', 'order', 'description', 'created_at']
        read_only_fields = ['organization', 'created_at']


class OrganizationSimpleSerializer(serializers.ModelSerializer):
    """
    Used by OrgCommunity serializers to show the name + LOGO.
    """

    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'logo', 'org_type']


class FormDataJSONField(serializers.JSONField):
    """
    Custom field that handles JSON data coming from FormData (which arrives as strings).
    """

    def to_internal_value(self, data):
        # If data is already a dict (standard JSON request), use parent logic
        if isinstance(data, dict):
            return super().to_internal_value(data)

        # If data is a string (FormData), try to parse it
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format.")

        return super().to_internal_value(data)


class OrganizationDetailSerializer(serializers.ModelSerializer):
    branding = FormDataJSONField(required=False)
    policies = FormDataJSONField(required=False)

    logo = serializers.ImageField(required=False, allow_null=True)

    membership_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    membership_period = serializers.ChoiceField(choices=Organization.MEMBERSHIP_PERIODS, required=False)
    membership_duration_value = serializers.IntegerField(required=False, allow_null=True)

    stats = serializers.SerializerMethodField()
    current_user_membership = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'org_type', 'description',
            'logo', 'approved',
            'branding', 'policies', 'created_at', 'stats',
            'current_user_membership',
            'membership_price', 'membership_period', 'membership_duration_value'
        ]
        read_only_fields = ['slug', 'approved', 'created_at', 'updated_at', 'branding', 'policies']

    def get_stats(self, obj):
        return {
            "students": OrgMembership.objects.filter(organization=obj, role="student", is_active=True).count(),
            "tutors": OrgMembership.objects.filter(organization=obj, role__in=["tutor", "admin", "owner"],
                                                   is_active=True).count(),
            "courses": Course.objects.filter(organization=obj, status='published').count(),
            "upcoming_events": 0
        }

    def get_current_user_membership(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        membership = OrgMembership.objects.filter(organization=obj, user=request.user, is_active=True).first()
        if membership:
            return {'is_active': membership.is_active, 'role': membership.role, 'organization_slug': obj.slug}
        return None

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class GuardianLinkSerializer(serializers.ModelSerializer):
    parent_details = OrgUserSerializer(source='parent', read_only=True)
    student_details = OrgUserSerializer(source='student', read_only=True)

    class Meta:
        model = GuardianLink
        fields = "__all__"


class OrgLevelInputSerializer(serializers.Serializer):
    """Simple validator for creating levels during org creation"""
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False, default=0)

class OrgCategoryInputSerializer(serializers.Serializer):
    """Simple validator for creating categories during org creation"""
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)


class OrganizationCreateSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(required=False, allow_null=True)

    levels = FormDataJSONField(required=False, write_only=True)
    categories = FormDataJSONField(required=False, write_only=True)
    branding = FormDataJSONField(required=False)
    policies = FormDataJSONField(required=False)

    class Meta:
        model = Organization
        fields = [
            'name', 'org_type', 'description', 'logo',
            'membership_price', 'membership_period', 'membership_duration_value',
            'branding', 'policies',
            'levels', 'categories', 'slug'
        ]
        read_only_fields = ['slug']

    def validate_levels(self, value):
        """Ensure the JSON structure for levels is valid"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise serializers.ValidationError("Levels must be valid JSON.")

        serializer = OrgLevelInputSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate_categories(self, value):
        """Ensure the JSON structure for categories is valid"""
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise serializers.ValidationError("Categories must be valid JSON.")

        serializer = OrgCategoryInputSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def create(self, validated_data):
        levels_data = validated_data.pop('levels', [])
        categories_data = validated_data.pop('categories', [])

        # Simple create works now because branding/policies are already dicts
        organization = Organization.objects.create(**validated_data)

        # Create nested objects
        if levels_data:
            OrgLevel.objects.bulk_create([OrgLevel(organization=organization, **item) for item in levels_data])

        if categories_data:
            OrgCategory.objects.bulk_create(
                [OrgCategory(organization=organization, **item) for item in categories_data])

        # Set Owner
        user = self.context['request'].user
        OrgMembership.objects.create(
            user=user, organization=organization, role='owner',
            is_active=True, payment_status='paid'
        )

        return organization


class OrgAdminInvitationSerializer(serializers.ModelSerializer):
    """
    Serializer for ADMINS to view their organization's sent invitations.
    """
    invited_user = OrgUserSerializer(read_only=True)
    invited_by = OrgUserSerializer(read_only=True)

    class Meta:
        model = OrgInvitation
        fields = ['id', 'invited_user', 'invited_by', 'role', 'status', 'created_at']


class StudentEnrollmentSerializer(serializers.Serializer):
    """
    Serializer used for the payment initiation step for students.
    Handles level selection and basic validation.
    """
    org_level_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        organization = self.context.get('organization')  # Assume view passes this
        user = self.context['request'].user
        org_level_id = data.get('org_level_id')

        if not organization or not organization.approved:
            raise serializers.ValidationError({"detail": "Organization not found or not approved."})

        if OrgMembership.objects.filter(user=user, organization=organization, role='student', is_active=True).exists():
            raise serializers.ValidationError(
                {"detail": "You are already an active student member of this organization."})

        if org_level_id:
            try:
                org_level = OrgLevel.objects.get(pk=org_level_id, organization=organization)
                data['org_level'] = org_level
            except OrgLevel.DoesNotExist:
                raise serializers.ValidationError({"org_level_id": "Invalid level selected for this organization."})

        # 4. Handle Payment Logic (Placeholder for Paystack/Revenue app integration)

        if organization.membership_price > 0:
            # Placeholder for revenue app call to initiate payment and get URL

            # Example:
            # revenue_details = initiate_payment(user, organization, organization.membership_price)
            # data['checkout_url'] = revenue_details['url']
            # data['payment_ref'] = revenue_details['reference']
            pass
        else:
            data['checkout_url'] = None

        data['organization'] = organization

        return data

    def create(self, validated_data):
        # NOTE: This method should be implemented to create a Pending OrgMembership
        # and a Transaction/Order, returning the checkout URL if payment is required.
        pass


class OrganizationListSerializer(serializers.ModelSerializer):
    is_member = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ('slug', 'name', 'org_type', 'description', 'membership_price', 'membership_period', 'is_member')

    def get_is_member(self, obj):
        """Checks if the requesting user is already an active member."""
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return False
        return OrgMembership.objects.filter(
            organization=obj, user=user, is_active=True
        ).exists()


class TeamMemberProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreatorProfile
        fields = ['display_name', 'bio', 'headline', 'profile_image', 'education', 'intro_video']


class OrgCategorySimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgCategory
        fields = ['id', 'name']


class OrgTeamMemberSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    email = serializers.EmailField(source='user.email')

    profile = serializers.SerializerMethodField()

    subjects = OrgCategorySimpleSerializer(many=True, read_only=True)

    class Meta:
        model = OrgMembership
        fields = [
            'id', 'role', 'date_joined',
            'first_name', 'last_name', 'email',
            'profile', 'subjects'
        ]

    def get_profile(self, obj):
        if hasattr(obj.user, 'creator_profile'):
            return TeamMemberProfileSerializer(obj.user.creator_profile, context=self.context).data
        return None




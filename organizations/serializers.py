import json
from rest_framework import serializers
from django.contrib.auth import get_user_model
from courses.models import Course
from events.models import Event
from org_community.models import OrgJoinRequest, OrgInvitation
from users.models import CreatorProfile
from .models import Organization, OrgMembership, GuardianLink, OrgLevel, OrgCategory

User = get_user_model()


class FormDataJSONField(serializers.JSONField):
    def to_internal_value(self, data):
        if data in [None, "", "null"]:
            return []
        if isinstance(data, (dict, list)):
            return super().to_internal_value(data)
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format.")
        return super().to_internal_value(data)


class OrganizationSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = "__all__"
        read_only_fields = ("slug", "approved", "created_at", "updated_at")

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None


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
        fields = ('id', 'user', 'organization', 'organization_name', 'organization_slug', 'role', 'is_active',
                  'date_joined')
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
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'logo', 'org_type', 'status']

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None


class OrganizationDetailSerializer(serializers.ModelSerializer):
    branding = FormDataJSONField(required=False)
    policies = FormDataJSONField(required=False)
    logo = serializers.SerializerMethodField()
    membership_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    membership_period = serializers.ChoiceField(choices=Organization.MEMBERSHIP_PERIODS, required=False)
    membership_duration_value = serializers.IntegerField(required=False, allow_null=True)
    stats = serializers.SerializerMethodField()
    current_user_membership = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'slug', 'org_type', 'description',
            'logo', 'approved', 'status',
            'branding', 'policies', 'created_at', 'stats',
            'current_user_membership',
            'membership_price', 'membership_period', 'membership_duration_value'
        ]
        read_only_fields = ['slug', 'approved', 'created_at', 'updated_at', 'branding', 'policies']

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

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


class GuardianLinkSerializer(serializers.ModelSerializer):
    parent_details = OrgUserSerializer(source='parent', read_only=True)
    student_details = OrgUserSerializer(source='student', read_only=True)

    class Meta:
        model = GuardianLink
        fields = "__all__"


class OrgLevelInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False, default=0)


class OrgCategoryInputSerializer(serializers.Serializer):
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
            'name', 'org_type', 'description', 'logo', 'status',
            'membership_price', 'membership_period', 'membership_duration_value',
            'branding', 'policies',
            'levels', 'categories', 'slug'
        ]
        read_only_fields = ['slug']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.logo:
            request = self.context.get('request')
            if request:
                ret['logo'] = request.build_absolute_uri(instance.logo.url)
            else:
                ret['logo'] = instance.logo.url
        return ret

    def validate_levels(self, value):
        serializer = OrgLevelInputSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate_categories(self, value):
        serializer = OrgCategoryInputSerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate(self, data):
        status = data.get('status', 'draft')

        if status != 'draft':
            errors = {}
            if not data.get('description') or len(data.get('description')) < 10:
                errors["description"] = "Description is required (min 10 chars) for submission."

            if not data.get('org_type'):
                errors["org_type"] = "Organization type is required for submission."

            period = data.get('membership_period', 'free')
            price = data.get('membership_price', 0)

            if period != 'free' and (price is None or price <= 0):
                errors["membership_price"] = "Price must be greater than 0 for paid memberships."

            if errors:
                raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        levels_data = validated_data.pop('levels', [])
        categories_data = validated_data.pop('categories', [])

        organization = Organization.objects.create(**validated_data)

        if levels_data:
            OrgLevel.objects.bulk_create(
                [OrgLevel(organization=organization, **item) for item in levels_data]
            )

        if categories_data:
            OrgCategory.objects.bulk_create(
                [OrgCategory(organization=organization, **item) for item in categories_data]
            )

        user = self.context['request'].user
        OrgMembership.objects.create(
            user=user, organization=organization, role='owner',
            is_active=True, payment_status='paid'
        )

        return organization


class OrgAdminInvitationSerializer(serializers.ModelSerializer):
    invited_user = OrgUserSerializer(read_only=True)
    invited_by = OrgUserSerializer(read_only=True)

    class Meta:
        model = OrgInvitation
        fields = ['id', 'invited_user', 'invited_by', 'role', 'status', 'created_at']


class StudentEnrollmentSerializer(serializers.Serializer):
    org_level_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        organization = self.context.get('organization')
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

        if organization.membership_price > 0:
            pass
        else:
            data['checkout_url'] = None

        data['organization'] = organization

        return data

    def create(self, validated_data):
        pass


class OrganizationListSerializer(serializers.ModelSerializer):
    is_member = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ('slug', 'name', 'org_type', 'logo', 'description', 'membership_price', 'membership_period',
                  'is_member', 'status')

    def get_logo(self, obj):
        if obj.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def get_is_member(self, obj):
        user = self.context.get('request').user
        if not user or not user.is_authenticated:
            return False
        return OrgMembership.objects.filter(
            organization=obj, user=user, is_active=True
        ).exists()


class TeamMemberProfileSerializer(serializers.ModelSerializer):
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = CreatorProfile
        fields = ['display_name', 'bio', 'headline', 'profile_image', 'education', 'intro_video']

    def get_profile_image(self, obj):
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None


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
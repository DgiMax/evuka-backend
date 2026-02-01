from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.db.models import Sum, Case, When, Avg
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.shortcuts import get_object_or_404


from courses.models import Lesson, LessonProgress, Course, Enrollment, Certificate
from courses.serializers import CourseListSerializer
from events.models import Event
from live.models import LiveLesson
from organizations.models import OrgMembership
from organizations.serializers import OrgMembershipSerializer
from revenue.models import Transaction, Payout, Wallet
from users.models import CreatorProfile, Subject, StudentProfile, NewsletterSubscriber, \
    BankingDetails, PublisherProfile

User = get_user_model()
signer = TimestampSigner()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def create(self, validated_data):
        user = User(
            username=validated_data["username"],
            email=validated_data["email"],
            is_active=False,
            is_verified=False,
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()

    def validate(self, data):
        token = data.get("token")
        try:
            email = signer.unsign(token, max_age=60 * 60 * 24)
            user = User.objects.get(email=email)
        except (BadSignature, SignatureExpired, User.DoesNotExist):
            raise serializers.ValidationError("Invalid or expired token.")
        data["user"] = user
        return data


class UserDetailSerializer(serializers.ModelSerializer):
    organizations = OrgMembershipSerializer(source='memberships', many=True, read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "is_verified",
            "is_tutor",
            "is_student",
            'organizations'
        )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        login_input = data.get("username")
        password = data.get("password")

        if '@' in login_input:
            try:
                user_obj = User.objects.get(email=login_input)
                login_input = user_obj.username
            except User.DoesNotExist:
                pass

        user = authenticate(username=login_input, password=password)

        if not user:
            raise serializers.ValidationError("Invalid credentials.")

        if not user.is_verified:
            raise serializers.ValidationError("Account not verified.")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        refresh = RefreshToken.for_user(user)

        user_data = UserDetailSerializer(user).data

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": user_data,
        }


class GoogleLoginSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value


class DashboardEventSerializer(serializers.ModelSerializer):
    banner_image = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['title', 'slug', 'start_time', 'event_type', 'banner_image']

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None


class DashboardCourseSerializer(serializers.ModelSerializer):
    tutor = serializers.CharField(source='creator.get_full_name', read_only=True)
    progress = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['title', 'slug', 'thumbnail', 'tutor', 'progress']

    def get_progress(self, obj):
        progress_map = self.context.get('progress_map', {})
        return progress_map.get(obj.id, 0)

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class ProfileCertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Certificate
        fields = ['id', 'course_title', 'issue_date', 'certificate_uid']


class ProfileOrgMembershipSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)

    class Meta:
        model = OrgMembership
        fields = ['id', 'organization_name', 'role']


class StudentProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for writing to the StudentProfile.
    """
    user = serializers.ReadOnlyField(source='user.username')
    avatar = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = StudentProfile
        fields = [
            'user',
            'avatar',
            'bio',
            'preferences',
            'created_at',
        ]
        read_only_fields = ['created_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)

        if instance.avatar:
            request = self.context.get('request')
            if request:
                ret['avatar'] = request.build_absolute_uri(instance.avatar.url)
            else:
                ret['avatar'] = instance.avatar.url
        return ret

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class StudentProfileReadSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for retrieving all data needed by the profile page UI.
    """
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    phone_number = serializers.CharField(source='user.phone_number',
                                         read_only=True)

    # Use SerializerMethodField for absolute URL
    avatar = serializers.SerializerMethodField()

    memberships = ProfileOrgMembershipSerializer(many=True, source='user.memberships', read_only=True)
    certificates = ProfileCertificateSerializer(many=True, source='user.certificates', read_only=True)

    enrolled_courses_count = serializers.SerializerMethodField()
    completed_courses_count = serializers.SerializerMethodField()
    certificates_count = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            'username', 'email', 'phone_number',
            'avatar', 'bio',
            'memberships', 'certificates',
            'enrolled_courses_count', 'completed_courses_count', 'certificates_count',
        ]

    def get_avatar(self, obj):
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def get_enrolled_courses_count(self, obj):
        """Counts actively enrolled courses."""
        return Enrollment.objects.filter(user=obj.user, status='active').count()

    def get_completed_courses_count(self, obj):
        """Counts courses with completed enrollment status."""
        return Enrollment.objects.filter(user=obj.user, status='completed').count()

    def get_certificates_count(self, obj):
        """Count certificates directly from the related manager."""
        return obj.user.certificates.count()


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['name', 'slug']


class CreatorProfilePublicSerializer(serializers.ModelSerializer):
    """
    Public-facing serializer for a tutor's profile page.
    Includes their bio, subjects, and list of published courses.
    """
    subjects = SubjectSerializer(many=True, read_only=True)
    courses = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = CreatorProfile
        fields = (
            'display_name', 'bio', 'profile_image', 'headline',
            'intro_video', 'education', 'subjects', 'courses', 'is_verified'
        )

    def get_profile_image(self, obj):
        if obj.profile_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_image.url)
            return obj.profile_image.url
        return None

    def get_courses(self, obj):
        courses_qs = Course.objects.filter(
            creator_profile=obj,
            organization__isnull=True,
            is_published=True
        ).order_by('-created_at')

        return CourseListSerializer(courses_qs, many=True, context=self.context).data


class CreatorProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the CreatorProfile.
    Handles create (POST) and update (PATCH/PUT).
    """
    subjects = serializers.ListField(
        child=serializers.CharField(max_length=100),
        write_only=True,
        required=False
    )
    subjects_list = SubjectSerializer(
        many=True,
        read_only=True,
        source='subjects'
    )
    user = serializers.ReadOnlyField(source='user.username')
    memberships = serializers.SerializerMethodField()

    # Use ImageField for writing, but override representation for reading
    profile_image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = CreatorProfile
        fields = [
            'user',
            'display_name',
            'headline',
            'bio',
            'profile_image',
            'intro_video',
            'education',
            'subjects',
            'subjects_list',
            'is_verified',
            'memberships',
        ]
        read_only_fields = ['is_verified']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.profile_image:
            request = self.context.get('request')
            if request:
                ret['profile_image'] = request.build_absolute_uri(instance.profile_image.url)
            else:
                ret['profile_image'] = instance.profile_image.url
        return ret

    def get_memberships(self, obj):
        """
        This is the custom method that populates the 'memberships' field.
        'obj' is the CreatorProfile instance.
        """
        creator_roles = ['owner', 'admin', 'tutor']

        queryset = obj.user.memberships.filter(
            role__in=creator_roles,
            is_active=True
        ).select_related('organization')

        return ProfileOrgMembershipSerializer(queryset, many=True).data

    def _handle_subjects(self, profile_instance, subject_names_list):
        profile_instance.subjects.clear()
        for subject_name in subject_names_list:
            name_cleaned = subject_name.strip()
            if name_cleaned:
                subject_obj, created = Subject.objects.get_or_create(
                    name__iexact=name_cleaned,
                    defaults={'name': name_cleaned}
                )
                profile_instance.subjects.add(subject_obj)

    def create(self, validated_data):
        subject_names = validated_data.pop('subjects', [])
        profile = CreatorProfile.objects.create(**validated_data)
        self._handle_subjects(profile, subject_names)
        return profile

    def update(self, instance, validated_data):
        subject_names = validated_data.pop('subjects', None)
        instance = super().update(instance, validated_data)

        if subject_names is not None:
            self._handle_subjects(instance, subject_names)

        return instance


class DashboardCourseMinimalSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True)
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "thumbnail",
            "student_count",
            "revenue",
            "rating_avg"
        ]

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class DashboardEventMinimalSerializer(serializers.ModelSerializer):
    start_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    attendee_count = serializers.IntegerField(read_only=True)
    banner_image = serializers.SerializerMethodField()
    revenue = serializers.FloatField(read_only=True)

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "slug",
            "start_time",
            "banner_image",
            "event_type",
            'attendee_count',
            'revenue'
        ]

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None


class DashboardLiveLessonSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="live_class.course.title", read_only=True)
    start_time = serializers.DateTimeField(source="start_datetime", format="%H:%M")
    date = serializers.DateTimeField(source="start_datetime", format="%Y-%m-%d")
    status = serializers.ReadOnlyField()

    class Meta:
        model = LiveLesson
        fields = [
            "id",
            "title",
            "course_title",
            "date",
            "start_time",
            "end_datetime",
            "status",
            "chat_room_id"
        ]

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ["id", "tx_type", "amount", "description", "created_at"]


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ["id", "amount", "status", "reference", "created_at", "processed_at"]


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ["balance", "currency"]


class WebSocketTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ['email', 'is_active', 'created_at']
        read_only_fields = ['is_active', 'created_at']


class StudentDashboardOrgSerializer(serializers.ModelSerializer):
    """
    Serializer to display organizations where the user is a student.
    Used in the Personal Dashboard.
    """
    name = serializers.CharField(source='organization.name', read_only=True)
    slug = serializers.CharField(source='organization.slug', read_only=True)
    level = serializers.CharField(source='level.name', default="General", read_only=True)
    logo = serializers.SerializerMethodField()

    class Meta:
        model = OrgMembership
        fields = ['name', 'slug', 'logo', 'level', 'expires_at']

    def get_logo(self, obj):
        if obj.organization.logo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.organization.logo.url)
            return obj.organization.logo.url
        return None


class PublicSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['name', 'slug']


class PublicTutorCourseSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer to display a list of courses on the tutor's profile.
    """
    category = serializers.CharField(source='global_subcategory.name', read_only=True)
    level = serializers.CharField(source='global_level.name', read_only=True)
    num_students = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = [
            'slug',
            'title',
            'thumbnail',
            'price',
            'rating_avg',
            'num_students',
            'category',
            'level'
        ]


class PublicTutorProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    subjects = PublicSubjectSerializer(many=True, read_only=True)
    courses = serializers.SerializerMethodField()

    # Aggregated Stats
    total_students = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = CreatorProfile
        fields = [
            'username',
            'display_name',
            'headline',
            'bio',
            'profile_image',
            'intro_video',
            'education',
            'is_verified',
            'subjects',
            'total_students',
            'total_reviews',
            'average_rating',
            'courses',
        ]

    def get_courses(self, obj):
        """
        Return only Published and Public courses associated with this profile.
        """
        courses = obj.courses.filter(status='published', is_public=True).annotate_popularity()
        return PublicTutorCourseSerializer(courses, many=True, context=self.context).data

    def get_total_students(self, obj):
        """Sum of students across all published courses."""
        # Note: We use the related_name 'courses' from the Course model
        return obj.courses.filter(status='published').aggregate(
            total=Sum('enrollments__id', distinct=True)  # Approximation based on enrollments
        )['total'] or 0

    def get_total_reviews(self, obj):
        """Sum of ratings across all courses."""
        return obj.courses.filter(status='published').aggregate(
            total=Sum('num_ratings')
        )['total'] or 0

    def get_average_rating(self, obj):
        """Weighted average rating across courses."""
        courses = obj.courses.filter(status='published')
        total_rating_sum = sum(c.rating_avg * c.num_ratings for c in courses)
        total_ratings_count = sum(c.num_ratings for c in courses)

        if total_ratings_count > 0:
            return round(total_rating_sum / total_ratings_count, 1)
        return 0.0


class PublicPublisherProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    books = serializers.SerializerMethodField()

    total_students = serializers.SerializerMethodField()  # Frontend calls them 'Students' or 'Readers'
    total_reviews = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    class Meta:
        model = PublisherProfile
        fields = [
            'username',
            'display_name',
            'headline',
            'bio',
            'profile_image',
            'intro_video',
            'website',
            'is_verified',
            'total_students',
            'total_reviews',
            'average_rating',
            'books',
        ]

    def get_books(self, obj):
        """Return only Published books associated with this publisher."""
        from books.serializers import BookListSerializer
        books = obj.books.filter(status='published').order_by('-created_at')
        return BookListSerializer(books, many=True, context=self.context).data

    def get_total_students(self, obj):
        """Sum of sales/readers across all published books."""
        return obj.books.filter(status='published').aggregate(
            total=Sum('sales_count')
        )['total'] or 0

    def get_total_reviews(self, obj):
        """Sum of readers/viewers who interacted."""
        return obj.books.filter(status='published').count()

    def get_average_rating(self, obj):
        """Average rating across all published books."""
        stats = obj.books.filter(status='published').aggregate(avg=Avg('rating_avg'))
        return round(stats['avg'] or 0.0, 1)


class PublisherProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublisherProfile
        fields = [
            'id',
            'display_name',
            'bio',
            'profile_image',
            'headline',
            'intro_video',
            'website',
            'is_verified'
        ]
        read_only_fields = ['is_verified']

    def create(self, validated_data):
        return PublisherProfile.objects.create(**validated_data)


class BankingDetailsInputSerializer(serializers.Serializer):
    """
    Validates the raw data coming from the frontend.
    """
    account_number = serializers.CharField(max_length=50, required=True)
    account_name = serializers.CharField(max_length=200, required=True)
    bank_code = serializers.CharField(
        max_length=50,
        required=True,
        help_text="Use 'MPESA' for mobile money or the bank's CBC code"
    )

class BankingDetailsViewSerializer(serializers.ModelSerializer):
    """
    Returns the safe, saved details for the dashboard.
    """
    class Meta:
        model = BankingDetails
        fields = ['bank_name', 'display_number', 'is_verified', 'updated_at']


class PublisherProfileManageView(generics.RetrieveUpdateAPIView, generics.CreateAPIView):
    """
    Manages Publisher Onboarding.
    - POST: Registers the user as a publisher.
    - GET/PUT: Manages profile details.
    """
    serializer_class = PublisherProfileSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Get the profile for the current user
        return get_object_or_404(PublisherProfile, user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Check if profile already exists to prevent duplicates
        if hasattr(request.user, 'publisher_profile'):
            return Response(
                {"error": "You already have a publisher profile."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

        # Activate the 'is_publisher' role flag on the User model
        user = self.request.user
        if not user.is_publisher:
            user.is_publisher = True
            user.save(update_fields=['is_publisher'])


class InstructorSearchSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(source='creator_profile.display_name', read_only=True)
    profile_image = serializers.ImageField(source='creator_profile.profile_image', read_only=True)
    headline = serializers.CharField(source='creator_profile.headline', read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'display_name', 'profile_image', 'headline')

class EventAnalyticsSerializer(serializers.ModelSerializer):
    registration_stats = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['id', 'title', 'start_time', 'event_type', 'event_status', 'registration_stats']

    def get_registration_stats(self, obj):
        return {
            "total": obj.registrations.count(),
            "attended": obj.registrations.filter(status='attended').count(),
            "revenue": float(obj.registrations.count() * obj.price) if obj.is_paid else 0
        }

class CourseAnalyticsSerializer(serializers.ModelSerializer):
    student_metrics = serializers.SerializerMethodField()
    revenue_metrics = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'slug', 'status', 'rating_avg', 'student_metrics', 'revenue_metrics']

    def get_student_metrics(self, obj):
        enrollments = obj.enrollments.all()
        total = enrollments.count()
        completed = enrollments.filter(status='completed').count()
        return {
            "total": total,
            "completed": completed,
            "completion_rate": round((completed / total * 100), 1) if total > 0 else 0
        }

    def get_revenue_metrics(self, obj):
        return {
            "total": float(obj.enrollments.count() * (obj.price or 0)),
            "price": float(obj.price or 0)
        }





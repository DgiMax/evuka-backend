from rest_framework import serializers
from django.utils import timezone
from courses.models import Course
from rest_framework.exceptions import PermissionDenied
from .models import (
    Event,
    EventRegistration,
    EventAttachment,
    EventAgenda,
    EventLearningObjective,
    EventRule,
)


class EventAttachmentSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()

    class Meta:
        model = EventAttachment
        fields = ["id", "file", "uploaded_by", "uploaded_at"]
        read_only_fields = ["uploaded_by", "uploaded_at"]

    def get_file(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class EventLearningObjectiveSerializer(serializers.ModelSerializer):
    text = serializers.CharField(allow_blank=True)

    class Meta:
        model = EventLearningObjective
        fields = ["id", "text"]


class EventAgendaSerializer(serializers.ModelSerializer):
    description = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = EventAgenda
        fields = ["id", "time", "title", "description", "order"]


class EventRuleSerializer(serializers.ModelSerializer):
    text = serializers.CharField(allow_blank=True)

    class Meta:
        model = EventRule
        fields = ["id", "title", "text"]


class SimpleCourseSerializer(serializers.ModelSerializer):
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ["id", "slug", "title", "price", "rating_avg", "num_ratings", "thumbnail"]

    def get_thumbnail(self, obj):
        if obj.thumbnail:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.thumbnail.url)
            return obj.thumbnail.url
        return None


class EventListSerializer(serializers.ModelSerializer):
    organizer_name = serializers.CharField(source="organizer.get_full_name", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    computed_status = serializers.CharField(read_only=True)
    banner_image = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "slug",
            "title",
            "start_time",
            "organizer_name",
            "banner_image",
            "course_title",
            "computed_status",
            "event_type",
            "price",
            "currency",
            "is_paid"
        ]

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None


class EventSerializer(serializers.ModelSerializer):
    attachments = EventAttachmentSerializer(many=True, read_only=True)
    agenda = EventAgendaSerializer(many=True, read_only=True)
    learning_objectives = EventLearningObjectiveSerializer(many=True, read_only=True)
    rules = EventRuleSerializer(many=True, read_only=True)
    registrations_count = serializers.IntegerField(source="registrations.count", read_only=True)
    organizer_name = serializers.CharField(source="organizer.get_username", read_only=True)
    course = SimpleCourseSerializer(read_only=True)
    is_full = serializers.BooleanField(read_only=True)
    is_registered = serializers.SerializerMethodField()
    has_ticket = serializers.SerializerMethodField()
    computed_status = serializers.CharField(read_only=True)
    banner_image = serializers.SerializerMethodField()
    meeting_link = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "title",
            "overview",
            "description",
            "event_type",
            "event_status",
            "computed_status",
            "location",
            "meeting_link",
            "start_time",
            "end_time",
            "timezone",
            "who_can_join",
            "banner_image",
            "is_paid",
            "price",
            "currency",
            "max_attendees",
            "registration_open",
            "registration_deadline",
            "course",
            "organizer",
            "organizer_name",
            "registrations_count",
            "is_full",
            "is_registered",
            "has_ticket",
            "attachments",
            "agenda",
            "learning_objectives",
            "rules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["organizer", "slug", "created_at", "updated_at"]

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None

    def get_meeting_link(self, obj):
        return None

    def get_is_registered(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return EventRegistration.objects.filter(
            event=obj, user=request.user, status="registered"
        ).exists()

    def get_has_ticket(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if obj.event_type == 'online':
            return False

        return EventRegistration.objects.filter(
            event=obj, user=request.user, status="registered"
        ).exists()


import json
from rest_framework import serializers
from django.utils import timezone
from .models import Event, EventLearningObjective, EventAgenda, EventRule
from courses.models import Course
from .serializers import EventSerializer, EventLearningObjectiveSerializer, EventAgendaSerializer, EventRuleSerializer

class CreateEventSerializer(serializers.ModelSerializer):
    course = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all()
    )

    learning_objectives = EventLearningObjectiveSerializer(
        many=True, write_only=True, required=False
    )
    agenda = EventAgendaSerializer(
        many=True, write_only=True, required=False
    )
    rules = EventRuleSerializer(
        many=True, write_only=True, required=False
    )

    class Meta:
        model = Event
        fields = [
            "id",
            "course",
            "title",
            "overview",
            "description",
            "event_type",
            "event_status",
            "location",
            "meeting_link",
            "start_time",
            "end_time",
            "timezone",
            "who_can_join",
            "banner_image",
            "is_paid",
            "price",
            "currency",
            "max_attendees",
            "registration_open",
            "registration_deadline",
            "learning_objectives",
            "agenda",
            "rules",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def to_internal_value(self, data):
        if hasattr(data, 'dict'):
            data = data.dict()

        json_fields = ['learning_objectives', 'agenda', 'rules']
        for field in json_fields:
            if field in data and isinstance(data[field], str) and data[field]:
                try:
                    data[field] = json.loads(data[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        if 'is_paid' in data and isinstance(data['is_paid'], str):
            data['is_paid'] = data['is_paid'].lower() == 'true'

        if 'registration_open' in data and isinstance(data['registration_open'], str):
            data['registration_open'] = data['registration_open'].lower() == 'true'

        return super().to_internal_value(data)

    def validate(self, attrs):
        start = attrs.get("start_time")
        end = attrs.get("end_time")
        course = attrs.get("course")
        who_can_join = attrs.get("who_can_join")

        if start and end and start >= end:
            raise serializers.ValidationError({"end_time": "End time must be after start time."})

        if who_can_join == "org_students" and (not course or not getattr(course, "organization", None)):
            raise serializers.ValidationError({
                "who_can_join": "Organization Students can only be selected if the course belongs to an organization."
            })

        return attrs

    def create(self, validated_data):
        objectives_data = validated_data.pop("learning_objectives", [])
        agenda_data = validated_data.pop("agenda", [])
        rules_data = validated_data.pop("rules", [])

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["organizer"] = request.user

        event = super().create(validated_data)

        if objectives_data:
            EventLearningObjective.objects.bulk_create(
                [EventLearningObjective(event=event, **obj) for obj in objectives_data]
            )

        if agenda_data:
            EventAgenda.objects.bulk_create(
                [EventAgenda(event=event, **item) for item in agenda_data]
            )

        if rules_data:
            EventRule.objects.bulk_create(
                [EventRule(event=event, **rule) for rule in rules_data]
            )

        if event.event_status == "pending_approval" and event.start_time and timezone.now() >= event.start_time:
            event.event_status = "cancelled"
            event.save()

        return event

    def to_representation(self, instance):
        return EventSerializer(instance, context=self.context).data

    def update(self, instance, validated_data):
        objectives_data = validated_data.pop("learning_objectives", [])
        agenda_data = validated_data.pop("agenda", [])
        rules_data = validated_data.pop("rules", [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        instance.learning_objectives.all().delete()
        instance.agenda.all().delete()
        instance.rules.all().delete()

        if objectives_data:
            EventLearningObjective.objects.bulk_create(
                [EventLearningObjective(event=instance, **obj) for obj in objectives_data]
            )
        if agenda_data:
            EventAgenda.objects.bulk_create(
                [EventAgenda(event=instance, **item) for item in agenda_data]
            )
        if rules_data:
            EventRule.objects.bulk_create(
                [EventRule(event=instance, **rule) for rule in rules_data]
            )

        return instance


class TutorEventDetailSerializer(serializers.ModelSerializer):
    course = SimpleCourseSerializer(read_only=True)
    attachments = EventAttachmentSerializer(many=True, read_only=True)
    agenda = EventAgendaSerializer(many=True, read_only=True)
    learning_objectives = EventLearningObjectiveSerializer(many=True, read_only=True)
    rules = EventRuleSerializer(many=True, read_only=True)
    computed_status = serializers.CharField(read_only=True)
    registrations_count = serializers.IntegerField(source="registrations.count", read_only=True)
    banner_image = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "slug",
            "title",
            "overview",
            "description",
            "event_type",
            "event_status",
            "computed_status",
            "location",
            "meeting_link",
            "start_time",
            "end_time",
            "timezone",
            "who_can_join",
            "banner_image",
            "is_paid",
            "price",
            "currency",
            "max_attendees",
            "registration_open",
            "registration_deadline",
            "course",
            "attachments",
            "agenda",
            "learning_objectives",
            "rules",
            "registrations_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["slug", "created_at", "updated_at"]

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None


class EventRegistrationSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = EventRegistration
        fields = [
            "id",
            "event",
            "event_title",
            "user",
            "status",
            "payment_status",
            "payment_reference",
            "registered_at",
            "updated_at",
        ]
        read_only_fields = ["status", "payment_status", "payment_reference"]

    def create(self, validated_data):
        event = validated_data["event"]
        user = validated_data["user"]

        if not event.can_user_register(user):
            raise serializers.ValidationError("Registration not allowed for this event.")

        if event.is_paid:
            validated_data["payment_status"] = "pending"
        else:
            validated_data["payment_status"] = "free"

        validated_data["status"] = "registered"
        return super().create(validated_data)


class FeaturedEventSerializer(serializers.ModelSerializer):
    banner_image = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "slug",
            "title",
            "description",
            "banner_image",
            "start_time",
            "location",
            "event_type",
            "is_paid",
            "price",
            "currency",
        ]

    def get_banner_image(self, obj):
        if obj.banner_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.banner_image.url)
            return obj.banner_image.url
        return None
from rest_framework import serializers
from .models import Wishlist
from courses.models import Course
from events.models import Event


class WishlistSerializer(serializers.ModelSerializer):
    # Use ReadOnlyField for simple strings
    item_title = serializers.ReadOnlyField()
    item_slug = serializers.ReadOnlyField()
    item_type = serializers.ReadOnlyField()

    # CRITICAL FIX: Use SerializerMethodField for the image to make it absolute
    item_image = serializers.SerializerMethodField()

    # For creation
    course_slug = serializers.CharField(write_only=True, required=False, allow_null=True)
    event_slug = serializers.CharField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Wishlist
        fields = [
            "id",
            "item_title",
            "item_image",
            "item_slug",
            "item_type",
            "created_at",
            # Write-only fields for creation
            "course_slug",
            "event_slug",
        ]

    def get_item_image(self, obj):
        """
        Takes the relative path from the model and builds a full URL.
        e.g., /media/x.jpg -> https://api.e-vuka.com/media/x.jpg
        """
        # Note: We are calling the property 'item_image_url' defined in the updated model
        relative_path = obj.item_image_url

        if relative_path:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(relative_path)
            return relative_path
        return None

    def validate(self, data):
        """
        Check that either a course_slug or an event_slug is provided, but not both.
        """
        course_slug = data.get("course_slug")
        event_slug = data.get("event_slug")

        if not course_slug and not event_slug:
            raise serializers.ValidationError("Either 'course_slug' or 'event_slug' is required.")

        if course_slug and event_slug:
            raise serializers.ValidationError("Provide only one of 'course_slug' or 'event_slug', not both.")

        return data

    def create(self, validated_data):
        user = self.context["request"].user
        course_slug = validated_data.get("course_slug")
        event_slug = validated_data.get("event_slug")

        if course_slug:
            try:
                course = Course.objects.get(slug=course_slug)
                # Using 'defaults' avoids a separate 'get' and 'create' call
                instance, _ = Wishlist.objects.get_or_create(user=user, course=course)
                return instance
            except Course.DoesNotExist:
                raise serializers.ValidationError({"course_slug": "Course not found."})

        if event_slug:
            try:
                event = Event.objects.get(slug=event_slug)
                instance, _ = Wishlist.objects.get_or_create(user=user, event=event)
                return instance
            except Event.DoesNotExist:
                raise serializers.ValidationError({"event_slug": "Event not found."})
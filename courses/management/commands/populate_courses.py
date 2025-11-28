from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone

from courses.models import (
    Course, Module, Lesson, GlobalCategory, GlobalLevel,
)
from organizations.models import Organization, OrgCategory, OrgLevel
from users.models import CreatorProfile

User = get_user_model()


class Command(BaseCommand):
    help = "Populate database with two dummy courses for testing."

    def handle(self, *args, **options):
        # --- Create a dummy creator ---
        creator, _ = User.objects.get_or_create(
            username="creator1",
            defaults={"email": "creator1@example.com", "first_name": "John", "last_name": "Doe"},
        )

        # Create CreatorProfile if not exists
        creator_profile, _ = CreatorProfile.objects.get_or_create(user=creator)

        # --- Global taxonomy ---
        cat1, _ = GlobalCategory.objects.get_or_create(
            name="Digital Storytelling", slug=slugify("Digital Storytelling"),
            defaults={"description": "Courses about creating digital stories."}
        )
        cat2, _ = GlobalCategory.objects.get_or_create(
            name="Creative Writing", slug=slugify("Creative Writing"),
            defaults={"description": "Courses to enhance writing and storytelling."}
        )

        lvl1, _ = GlobalLevel.objects.get_or_create(
            name="Beginner", order=1, defaults={"description": "Entry level content."}
        )
        lvl2, _ = GlobalLevel.objects.get_or_create(
            name="Intermediate", order=2, defaults={"description": "For learners with some experience."}
        )

        # --- Organization setup ---
        # --- Organization setup ---
        org, _ = Organization.objects.get_or_create(
            name="Swahili Arts Institute",
            defaults={"description": "Promoting Swahili storytelling culture."}
        )

        org_cat, _ = OrgCategory.objects.get_or_create(
            organization=org,
            name="Cultural Studies",
            defaults={"description": "Courses related to Swahili culture and heritage."}
        )

        org_lvl, _ = OrgLevel.objects.get_or_create(
            organization=org,
            name="Professional",
            order=1,
            defaults={"description": "Advanced courses for professionals."}
        )

        # -------------------------------
        # 1️⃣ Independent Course
        # -------------------------------
        independent_course, _ = Course.objects.get_or_create(
            title="Swahili Digital Storytelling Basics",
            defaults={
                "slug": slugify("Swahili Digital Storytelling Basics"),
                "short_description": "Learn to tell compelling Swahili stories digitally.",
                "long_description": "This course introduces learners to the art of digital storytelling using text, sound, and visuals.",
                "learning_objectives": [
                    "Understand key elements of Swahili storytelling",
                    "Develop original story ideas in Swahili",
                    "Record and edit simple voiceovers"
                ],
                "thumbnail": "https://placehold.co/600x400",
                "promo_video": "https://example.com/video1.mp4",
                "creator": creator,
                "creator_profile": creator_profile,
                "global_category": cat1,
                "global_level": lvl1,
                "price": 19.99,
                "is_published": True,
            },
        )

        module1 = Module.objects.create(
            course=independent_course,
            title="Introduction to Digital Storytelling",
            description="Basics of storytelling and narrative structure.",
            order=1,
        )

        Lesson.objects.create(
            module=module1,
            title="The Power of Story",
            content="Stories shape culture. Learn why storytelling matters.",
            order=1,
            estimated_duration_minutes=10,
        )
        Lesson.objects.create(
            module=module1,
            title="Story Elements",
            content="Explore character, setting, conflict, and resolution.",
            order=2,
            estimated_duration_minutes=15,
        )

        # -------------------------------
        # 2️⃣ Organization Course
        # -------------------------------
        org_course, _ = Course.objects.get_or_create(
            title="Advanced Swahili Storytelling Workshop",
            defaults={
                "slug": slugify("Advanced Swahili Storytelling Workshop"),
                "short_description": "Deep dive into Swahili cultural narratives.",
                "long_description": "A workshop-style course blending traditional Swahili oral traditions with modern digital media techniques.",
                "learning_objectives": [
                    "Analyze traditional Swahili storytelling techniques",
                    "Create and perform short digital stories",
                    "Collaborate with peers to produce cultural narratives"
                ],
                "thumbnail": "https://placehold.co/600x400",
                "promo_video": "https://example.com/video2.mp4",
                "creator": creator,
                "creator_profile": creator_profile,
                "organization": org,
                "org_category": org_cat,
                "org_level": org_lvl,
                "global_category": cat2,
                "global_level": lvl2,
                "price": 49.99,
                "is_published": True,
            },
        )

        module2 = Module.objects.create(
            course=org_course,
            title="Cultural Roots of Swahili Stories",
            description="Dive into cultural foundations of storytelling.",
            order=1,
        )

        Lesson.objects.create(
            module=module2,
            organization=org,
            title="Understanding Oral Traditions",
            content="Explore how oral traditions shape Swahili storytelling identity.",
            order=1,
            estimated_duration_minutes=20,
        )
        Lesson.objects.create(
            module=module2,
            organization=org,
            title="Modern Storytelling Tools",
            content="Use digital tools to bring traditional stories to life.",
            order=2,
            estimated_duration_minutes=25,
        )

        self.stdout.write(self.style.SUCCESS("✅ Successfully populated two sample courses!"))

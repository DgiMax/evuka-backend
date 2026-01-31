import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils import timezone
from books.models import Book, BookCategory, BookSubCategory
from users.models import PublisherProfile

User = get_user_model()

class Command(BaseCommand):
    help = 'Populates the database with 4 sample books for the user james'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting population...")

        # 1. Get or Create User 'james'
        james, created = User.objects.get_or_create(
            username='james',
            defaults={'email': 'james@example.com', 'is_staff': True}
        )
        if created:
            james.set_password('password123')
            james.save()
            self.stdout.write(self.style.SUCCESS(f"Created user: {james.username}"))

        # 2. Ensure james has a PublisherProfile
        publisher, _ = PublisherProfile.objects.get_or_create(
            user=james,
            defaults={
                'display_name': 'James Publishing House',
                'bio': 'Expert in technical and business literature.'
            }
        )

        # 3. Create Categories and Subcategories
        tech_cat, _ = BookCategory.objects.get_or_create(name="Technology")
        biz_cat, _ = BookCategory.objects.get_or_create(name="Business")

        prog_sub, _ = BookSubCategory.objects.get_or_create(category=tech_cat, name="Programming")
        startup_sub, _ = BookSubCategory.objects.get_or_create(category=biz_cat, name="Startups")

        # 4. Book Data
        books_data = [
            {
                "title": "Mastering Django Rest Framework",
                "subtitle": "Build professional APIs with Python",
                "authors": "James K. Python",
                "price": Decimal("2500.00"),
                "is_free": False,
                "format": "pdf",
                "level": "intermediate",
                "category": tech_cat,
                "subcategory": prog_sub,
                "isbn": "978-3-16-148410-0"
            },
            {
                "title": "The Solo Developer Guide",
                "subtitle": "From Code to Cash",
                "authors": "James Dev",
                "price": Decimal("0.00"),
                "is_free": True,
                "format": "epub",
                "level": "all_levels",
                "category": tech_cat,
                "subcategory": prog_sub,
                "isbn": "978-1-23-456789-0"
            },
            {
                "title": "Kenyan Startup Ecosystem",
                "subtitle": "Market Entry and Scaling in Nairobi",
                "authors": "James Mwangi",
                "price": Decimal("1800.00"),
                "is_free": False,
                "format": "pdf",
                "level": "advanced",
                "category": biz_cat,
                "subcategory": startup_sub,
                "isbn": "978-0-12-345678-9"
            },
            {
                "title": "Cinematic Animations with AI",
                "subtitle": "Generating Interior Design Showcases",
                "authors": "James Graphics",
                "price": Decimal("3200.00"),
                "is_free": False,
                "format": "audio",
                "level": "beginner",
                "category": tech_cat,
                "subcategory": prog_sub,
                "isbn": "978-9-87-654321-0"
            }
        ]

        # 5. Populate Books
        for data in books_data:
            book, created = Book.objects.get_or_create(
                title=data["title"],
                created_by=james,
                publisher_profile=publisher,
                defaults={
                    "subtitle": data["subtitle"],
                    "authors": data["authors"],
                    "price": data["price"],
                    "is_free": data["is_free"],
                    "book_format": data["format"],
                    "reading_level": data["level"],
                    "isbn": data["isbn"],
                    "status": "published",
                    "short_description": f"A comprehensive guide on {data['title']}.",
                    "long_description": f"This book covers everything you need to know about {data['title']} in a professional environment.",
                    "table_of_contents": [
                        {"title": "Introduction", "page": 1},
                        {"title": "Getting Started", "page": 15},
                        {"title": "Advanced Techniques", "page": 45},
                        {"title": "Conclusion", "page": 100}
                    ],
                    "tags": ["trending", "educational", "professional"],
                    "publication_date": timezone.now().date()
                }
            )

            if created:
                book.categories.add(data["category"])
                book.subcategories.add(data["subcategory"])
                self.stdout.write(self.style.SUCCESS(f"Successfully populated: {book.title}"))
            else:
                self.stdout.write(self.style.WARNING(f"Book already exists: {book.title}"))

        self.stdout.write(self.style.SUCCESS("Population complete!"))
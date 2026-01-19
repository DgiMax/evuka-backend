import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator
from users.models import PublisherProfile


class BookCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Book Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BookSubCategory(models.Model):
    category = models.ForeignKey(BookCategory, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('category', 'name')
        verbose_name_plural = "Book Subcategories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.name} > {self.name}"


class Book(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    FORMAT_CHOICES = [
        ('pdf', 'PDF eBook'),
        ('epub', 'ePub eBook'),
        ('audio', 'Audiobook'),
    ]

    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('all_levels', 'All Levels'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="books_created")
    publisher_profile = models.ForeignKey(PublisherProfile, on_delete=models.CASCADE, related_name="books")

    slug = models.SlugField(max_length=255, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    isbn = models.CharField(max_length=20, blank=True, null=True)
    publication_date = models.DateField(null=True, blank=True)

    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True)
    authors = models.CharField(max_length=255, blank=True)

    categories = models.ManyToManyField(BookCategory, related_name="books", blank=True)
    subcategories = models.ManyToManyField(BookSubCategory, related_name="books", blank=True)
    tags = models.JSONField(default=list, blank=True)

    short_description = models.TextField(max_length=500, blank=True)
    long_description = models.TextField(blank=True)
    table_of_contents = models.JSONField(default=list, blank=True)
    reading_level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='all_levels')

    cover_image = models.ImageField(upload_to='covers/', null=True, blank=True)
    book_format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='pdf')

    book_file = models.FileField(upload_to='secure_books/', null=True, blank=True)
    preview_file = models.FileField(upload_to='public_previews/', null=True, blank=True)

    currency = models.CharField(max_length=3, default='KES')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_free = models.BooleanField(default=False)

    discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_start_date = models.DateTimeField(null=True, blank=True)
    discount_end_date = models.DateTimeField(null=True, blank=True)

    referral_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(50)]
    )

    view_count = models.PositiveIntegerField(default=0)
    sales_count = models.PositiveIntegerField(default=0)
    rating_avg = models.FloatField(default=0.0)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.title}-{str(uuid.uuid4())[:6]}")
        if self.price == 0:
            self.is_free = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class CourseBook(models.Model):
    INTEGRATION_CHOICES = [
        ('included', 'Included in Course Price'),
        ('required_purchase', 'Student Must Buy Separately'),
        ('optional', 'Optional Resource'),
    ]

    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name="course_books")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="course_integrations")

    integration_type = models.CharField(max_length=20, choices=INTEGRATION_CHOICES, default='required_purchase')

    applied_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course', 'book')

    def save(self, *args, **kwargs):
        if not self.pk and self.book:
            self.applied_commission_percent = self.book.referral_commission_percent
        super().save(*args, **kwargs)


class BookAccess(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="library")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="readers")
    granted_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=50, default='direct_purchase')

    class Meta:
        unique_together = ('user', 'book')
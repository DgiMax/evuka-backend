from django.db import models
from django.utils.text import slugify


class HelpCategory(models.Model):
    ICON_CHOICES = [
        ('book', 'Courses & Content'),
        ('credit-card', 'Billing & Payments'),
        ('video', 'Live Classes'),
        ('shield', 'Account & Security'),
        ('settings', 'General Settings'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.CharField(max_length=255)
    icon = models.CharField(max_length=50, choices=ICON_CHOICES, default='book')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name_plural = "Help Categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class HelpArticle(models.Model):
    category = models.ForeignKey(HelpCategory, related_name='articles', on_delete=models.CASCADE)
    question = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    answer = models.TextField(help_text="HTML or Markdown supported")
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False, help_text="Show on Help Center homepage")

    views_count = models.PositiveIntegerField(default=0)
    helpful_count = models.PositiveIntegerField(default=0)
    not_helpful_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.question)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.question
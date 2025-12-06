from django.db import models

class HelpCategory(models.Model):
    ICON_CHOICES = [
        ('book', 'Courses & Content'),
        ('credit-card', 'Billing & Payments'),
        ('video', 'Live Classes'),
        ('shield', 'Account & Security'),
        ('settings', 'General Settings'),
    ]

    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    icon = models.CharField(max_length=50, choices=ICON_CHOICES, default='book')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']
        verbose_name_plural = "Help Categories"

    def __str__(self):
        return self.name

class HelpArticle(models.Model):
    category = models.ForeignKey(HelpCategory, related_name='articles', on_delete=models.CASCADE)
    question = models.CharField(max_length=255)
    answer = models.TextField(help_text="HTML or Markdown supported")
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question
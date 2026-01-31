from rest_framework import serializers
from django.db.models import Count
from books.models import BookCategory, BookSubCategory
from courses.models import GlobalSubCategory, GlobalCategory

# 1. Course Subcategory Serializer
class NavLinkSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSubCategory
        fields = ['name', 'slug']

# 2. Book Subcategory Serializer (The one that was missing)
class NavLinkBookSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookSubCategory
        fields = ['name', 'slug']

# 3. Course Category Serializer
class NavLinkCourseCategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = GlobalCategory
        fields = ['name', 'slug', 'subcategories']

    def get_subcategories(self, obj):
        subs = obj.subcategories.annotate(
            item_count=Count('courses')
        ).order_by('-item_count')[:10]
        return NavLinkSubCategorySerializer(subs, many=True).data

# 4. Book Category Serializer
class NavLinkBookCategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = BookCategory
        fields = ['name', 'slug', 'subcategories']

    def get_subcategories(self, obj):
        subs = obj.subcategories.annotate(
            item_count=Count('books')
        ).order_by('-item_count')[:10]
        # This line now makes sense because NavLinkBookSubCategorySerializer is defined above
        return NavLinkBookSubCategorySerializer(subs, many=True).data
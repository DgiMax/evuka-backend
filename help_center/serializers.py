from rest_framework import serializers
from .models import HelpCategory, HelpArticle


class HelpArticleSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = HelpArticle
        fields = [
            'id', 'category', 'category_name', 'question', 'slug',
            'answer', 'helpful_count', 'not_helpful_count', 'views_count'
        ]


class HelpCategorySerializer(serializers.ModelSerializer):
    articles = HelpArticleSerializer(many=True, read_only=True)

    class Meta:
        model = HelpCategory
        fields = ['id', 'name', 'slug', 'description', 'icon', 'articles']
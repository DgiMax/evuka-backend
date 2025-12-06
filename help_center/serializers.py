from rest_framework import serializers
from .models import HelpCategory, HelpArticle

class HelpArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpArticle
        fields = ['id', 'question', 'answer']

class HelpCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpCategory
        fields = ['id', 'name', 'description', 'icon']
import json
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Book, BookCategory, BookSubCategory, BookAccess, CourseBook

User = get_user_model()


class PublisherSummarySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    publisher_name = serializers.CharField(source='display_name', read_only=True)
    publisher_logo = serializers.ImageField(source='profile_image', read_only=True)

    class Meta:
        from users.models import PublisherProfile
        model = PublisherProfile
        fields = ("publisher_name", "bio", "username", "publisher_logo")


class BookCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookCategory
        fields = ("id", "name", "slug")


class BookSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookSubCategory
        fields = ("id", "name", "slug", "category")


class BookSubCategoryOptionSerializer(serializers.ModelSerializer):
    parent_id = serializers.ReadOnlyField(source='category.id')

    class Meta:
        model = BookSubCategory
        fields = ('id', 'name', 'slug', 'parent_id')


class BookListSerializer(serializers.ModelSerializer):
    publisher = PublisherSummarySerializer(source='publisher_profile', read_only=True)
    categories = BookCategorySerializer(many=True, read_only=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    rating_avg = serializers.FloatField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_owned = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = (
            "id", "slug", "title", "authors", "cover_image",
            "short_description", "publisher", "rating_avg",
            "price", "currency", "is_free", "book_format",
            "categories", "status", "status_display", "is_owned",
            "discount_price"
        )

    def get_is_owned(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return BookAccess.objects.filter(user=request.user, book=obj).exists()
        return False


class BookDetailSerializer(serializers.ModelSerializer):
    publisher = PublisherSummarySerializer(source='publisher_profile', read_only=True)
    categories = BookCategorySerializer(many=True, read_only=True)
    subcategories = BookSubCategorySerializer(many=True, read_only=True)
    is_owned = serializers.SerializerMethodField()
    preview_file_url = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = (
            "id", "slug", "title", "subtitle", "authors",
            "cover_image", "short_description", "long_description",
            "table_of_contents", "publisher",
            "rating_avg", "view_count", "sales_count",
            "price", "currency", "is_free", "discount_price",
            "referral_commission_percent",
            "book_format", "reading_level", "status",
            "categories", "subcategories", "tags",
            "created_at", "updated_at", "is_owned", "preview_file_url",
            "isbn", "publication_date"
        )

    def get_is_owned(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return BookAccess.objects.filter(user=request.user, book=obj).exists()
        return False

    def get_preview_file_url(self, obj):
        if obj.preview_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.preview_file.url)
            return obj.preview_file.url
        return None


class BookCreateUpdateSerializer(serializers.ModelSerializer):
    authors = serializers.CharField(required=False, allow_blank=True)
    isbn = serializers.CharField(required=False, allow_blank=True)
    short_description = serializers.CharField(required=False, allow_blank=True)

    cover_image = serializers.ImageField(required=False, allow_null=True)
    book_file = serializers.FileField(required=False, allow_null=True)
    preview_file = serializers.FileField(required=False, allow_null=True)

    categories = serializers.PrimaryKeyRelatedField(
        queryset=BookCategory.objects.all(), many=True, required=False
    )
    subcategories = serializers.PrimaryKeyRelatedField(
        queryset=BookSubCategory.objects.all(), many=True, required=False
    )

    tags = serializers.JSONField(required=False)
    table_of_contents = serializers.JSONField(required=False)

    slug = serializers.SlugField(read_only=True)
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Book
        fields = (
            "id", "slug",
            "title", "subtitle", "authors",
            "categories", "subcategories", "tags",
            "short_description", "long_description", "table_of_contents",
            "reading_level", "cover_image", "book_format",
            "book_file", "preview_file",
            "currency", "price", "is_free", "discount_price",
            "referral_commission_percent",
            "discount_start_date", "discount_end_date",
            "status", "isbn", "publication_date"
        )

    def to_internal_value(self, data):
        if hasattr(data, 'dict'):
            mutable_data = data.copy()
        else:
            mutable_data = data.copy()

        for field in ['tags', 'table_of_contents']:
            if field in mutable_data:
                value = mutable_data[field]
                if isinstance(value, str):
                    if not value.strip():
                        mutable_data[field] = [] if field == 'table_of_contents' else {}
                    else:
                        try:
                            mutable_data[field] = json.loads(value)
                        except ValueError:
                            pass

        return super().to_internal_value(mutable_data)

    def validate_isbn(self, value):
        if not value:
            return ""
        clean_isbn = value.replace('-', '').replace(' ', '')
        if len(clean_isbn) not in [10, 13]:
            raise serializers.ValidationError("ISBN must be valid 10 or 13 digits.")
        return clean_isbn

    def validate_table_of_contents(self, value):
        if not value:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError("TOC must be a list of chapters.")
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each TOC item must be an object.")
            if 'title' not in item:
                raise serializers.ValidationError("TOC items must have a 'title'.")
            item['level'] = int(item.get('level', 0))
        return value

    def validate(self, data):
        if data.get('is_free', False):
            data['price'] = 0

        incoming_status = data.get('status')
        current_instance = self.instance
        effective_status = incoming_status if incoming_status else (
            current_instance.status if current_instance else 'draft')

        if effective_status == 'published':
            missing_fields = []

            if not data.get('title') and (not current_instance or not current_instance.title):
                missing_fields.append("Title")
            if not data.get('authors') and (not current_instance or not current_instance.authors):
                missing_fields.append("Authors")

            book_fmt = data.get('book_format') or (current_instance.book_format if current_instance else 'pdf')
            has_file = data.get('book_file') or (current_instance and current_instance.book_file)
            if book_fmt != 'audio' and not has_file:
                missing_fields.append("Book File")

            has_cover = data.get('cover_image') or (current_instance and current_instance.cover_image)
            if not has_cover:
                missing_fields.append("Cover Image")

            is_free = data.get('is_free') if 'is_free' in data else (
                current_instance.is_free if current_instance else False)
            price = data.get('price') if 'price' in data else (current_instance.price if current_instance else 0)

            if not is_free and price <= 0:
                missing_fields.append("Price")

            if missing_fields:
                data['status'] = 'draft'

        return data


class CourseBookSerializer(serializers.ModelSerializer):
    book_details = BookListSerializer(source='book', read_only=True)

    class Meta:
        model = CourseBook
        fields = (
            'id', 'book', 'course', 'integration_type',
            'applied_commission_percent', 'created_at', 'book_details'
        )
        read_only_fields = ('applied_commission_percent', 'created_at')
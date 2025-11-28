# your_app/utils/search_utils.py

from django.db.models import Q
from django.utils import timezone


def sqlite_search_model(model_class, query, public_filter, title_field, slug_field, description_field=None, limit=5):
    """
    Performs a manually scored search for a single model, compatible with SQLite.

    Args:
        model_class (Model): The Django Model to search (Course, Event, etc.).
        query (str): The user's search query.
        public_filter (Q): A Q object defining visibility (published, approved, etc.).
        title_field (str): The name of the title/name field (e.g., 'title', 'name').
        slug_field (str): The name of the slug field (e.g., 'slug').
        description_field (str, optional): The name of the main description field.
        limit (int): The maximum number of results to return.

    Returns:
        list: A sorted list of dictionaries with search results and scores.
    """
    if not query:
        return []

    # Define score weights for field priority (Manual Ranking)
    TITLE_SCORE = 3
    DESCRIPTION_SCORE = 1

    combined_results = []

    # Start with the public/visibility filter
    qs = model_class.objects.filter(public_filter)

    # --- 1. Title/Name Match (Highest Score) ---
    title_q = Q(**{f'{title_field}__icontains': query})
    title_matches = qs.filter(title_q).distinct()

    for item in title_matches:
        combined_results.append({
            'id': item.pk,
            'model': model_class.__name__.lower(),
            'title': getattr(item, title_field),
            'slug': getattr(item, slug_field),
            'score': TITLE_SCORE,
        })

    # --- 2. Description Match (Lower Score) ---
    if description_field:
        description_q = Q(**{f'{description_field}__icontains': query})

        # Exclude results already found in the title search to avoid duplicates
        description_matches = qs.filter(description_q).exclude(pk__in=[r['id'] for r in combined_results]).distinct()

        for item in description_matches:
            combined_results.append({
                'id': item.pk,
                'model': model_class.__name__.lower(),
                'title': getattr(item, title_field),
                'slug': getattr(item, slug_field),
                'score': DESCRIPTION_SCORE,
            })

    # Sort results primarily by score (manual weight), then by title
    combined_results.sort(key=lambda x: (x['score'], x['title']), reverse=True)

    return combined_results[:limit]
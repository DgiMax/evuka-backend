from django.conf import settings
from django_bunny_storage.storage import BunnyStorage

class ConnectedBunnyStorage(BunnyStorage):
    """
    A wrapper around BunnyStorage that adds the missing url() method
    so Django knows how to display images.
    """
    def url(self, name):
        # Combine the Pull Zone URL (from settings) with the file name
        base_url = getattr(settings, 'BUNNY_PULL_ZONE_URL', '')
        if not base_url:
            raise ValueError("BUNNY_PULL_ZONE_URL must be set in settings/env")

        # Ensure base_url ends with slash and name doesn't start with one
        if not base_url.endswith('/'):
            base_url += '/'

        return f"{base_url}{name}"
from organizations.models import Organization


class ActiveOrganizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Default to None (Personal Context)
        request.active_organization = None

        # 2. Read the header sent by the frontend
        slug = request.headers.get('X-Organization-Slug')

        if slug and request.user.is_authenticated:
            try:
                # 3. Security Check: Find the org IF the user is a member
                organization = Organization.objects.get(
                    slug=slug,
                    memberships__user=request.user,
                    memberships__is_active=True
                )

                # 4. Success: Attach the org to the request
                request.active_organization = organization

            except Organization.DoesNotExist:
                # Failure: User is not a member or org doesn't exist.
                # request.active_organization stays None.
                pass

        response = self.get_response(request)
        return response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Sum
from .models_finance import PendingEarning

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_tutor_earnings_dashboard(request, org_slug):
    pending_total = PendingEarning.objects.filter(
        organization__slug=org_slug,
        tutor=request.user,
        is_cleared=False
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    paid_total = PendingEarning.objects.filter(
        organization__slug=org_slug,
        tutor=request.user,
        is_cleared=True
    ).aggregate(Sum('amount'))['amount__sum'] or 0

    recent_earnings = PendingEarning.objects.filter(
        organization__slug=org_slug,
        tutor=request.user
    ).order_by('-created_at')[:10]

    return Response({
        "pending_balance": pending_total,
        "lifetime_earnings": paid_total,
        "recent_history": [
            {
                "date": e.created_at,
                "course": e.source_order_item.course.title if e.source_order_item and e.source_order_item.course else "Unknown Item",
                "amount": e.amount,
                "status": "PAID" if e.is_cleared else "PENDING"
            } for e in recent_earnings
        ]
    })
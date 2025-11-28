from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from decimal import Decimal

from organizations.models import OrgMembership
from .models import Wallet, Transaction, Payout
from .serializers import WalletSerializer, PayoutSerializer
from .services import initiate_payout


class RevenueOverviewView(APIView):
    """
    Returns wallet, transactions, and payout summary based on context:
    - Personal account
    - Organization account (tutor, admin, owner)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        active_org = getattr(request, "active_organization", None)
        response_data = {}

        if hasattr(user, "wallet"):
            response_data["personal_wallet"] = WalletSerializer(user.wallet).data
        else:
            response_data["personal_wallet"] = None

        if active_org:
            membership = OrgMembership.objects.filter(
                user=user, organization=active_org, is_active=True
            ).first()

            if not membership:
                return Response(
                    {"detail": "You are not a member of this organization."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if hasattr(active_org, "wallet"):
                org_wallet = active_org.wallet
                response_data["organization_wallet"] = WalletSerializer(org_wallet).data
            else:
                response_data["organization_wallet"] = None

            if membership.role in ["admin", "owner"]:
                response_data["view"] = "organization_admin"
                response_data["message"] = f"You are viewing {active_org.name}'s full financial summary."
            else:
                response_data["view"] = "organization_member"
                response_data["message"] = (
                    f"You are viewing your personal earnings under {active_org.name}."
                )
        else:
            response_data["view"] = "personal"
            response_data["message"] = "You are viewing your personal earnings."

        return Response(response_data, status=status.HTTP_200_OK)


class InitiatePayoutView(APIView):
    """
    Allows a user to withdraw from their personal or organization wallet.
    Only org admins/owners can withdraw from org wallet.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount = Decimal(request.data.get("amount", "0"))
        context = request.data.get("context", "personal")
        user = request.user

        if amount <= 0:
            return Response({"detail": "Invalid amount."}, status=400)

        if context == "personal":
            if not hasattr(user, "wallet"):
                return Response({"detail": "Wallet not found."}, status=400)
            wallet = user.wallet

        elif context == "organization":
            active_org = getattr(request, "active_organization", None)
            if not active_org:
                return Response(
                    {"detail": "No active organization context."}, status=400
                )

            membership = OrgMembership.objects.filter(
                user=user, organization=active_org, is_active=True
            ).first()

            if not membership:
                return Response(
                    {"detail": "You are not a member of this organization."}, status=403
                )

            if membership.role not in ["admin", "owner"]:
                return Response(
                    {
                        "detail": "Only organization admins or owners can initiate organization payouts."
                    },
                    status=403,
                )

            if not hasattr(active_org, "wallet"):
                return Response(
                    {"detail": "Organization wallet not found."}, status=400
                )

            wallet = active_org.wallet
        else:
            return Response({"detail": "Invalid payout context."}, status=400)

        try:
            payout = initiate_payout(wallet, amount)
            return Response(PayoutSerializer(payout).data, status=201)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
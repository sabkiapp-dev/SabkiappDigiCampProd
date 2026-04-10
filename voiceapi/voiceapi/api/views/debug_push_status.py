"""
Light-weight endpoint meant ONLY for manual testing of the CallStatusPusher.

POST whatever payload you want and we will forward it to
`staging.sabkiapp.com/survey/verify-family-member` via the reusable helper.
"""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status

# open endpoint – no auth
@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def test_push_call_status(request):
    from api.utils.call_status_pusher import CallStatusPusher  # local import keeps startup fast

    payload = request.data
    print("🔄  forwarding payload →", payload)          # prints to console only

    ok = CallStatusPusher.push(payload)
    if ok:
        return Response({"detail": "Forwarded successfully"}, status=status.HTTP_200_OK)
    return Response({"detail": "Remote server returned non-200"}, status=status.HTTP_502_BAD_GATEWAY)

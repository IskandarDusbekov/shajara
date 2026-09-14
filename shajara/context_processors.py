from .models import ConnectionRequest


def pending_requests(request):
    if not request.user.is_authenticated:
        return {"pending_count": 0, "email_verified": True, "tour_pending": False}
    count = ConnectionRequest.objects.filter(to_user=request.user, status="pending").count()
    profile = getattr(request.user, "profile", None)
    email_verified = bool(profile and profile.email_verified)
    context = {"pending_count": count, "email_verified": email_verified,
               "tour_pending": bool(profile and not profile.tour_done)}
    if request.user.is_staff:
        from .models import MatchCandidate
        context["adm_pending_matches"] = MatchCandidate.objects.filter(status="pending").count()
        match = getattr(request, "resolver_match", None)
        if match and match.namespace == "boshqaruv":
            from .models import UserProfile
            from .presence import online_since
            context["adm_online"] = UserProfile.objects.filter(last_seen__gte=online_since(), user__is_active=True).count()
    return context

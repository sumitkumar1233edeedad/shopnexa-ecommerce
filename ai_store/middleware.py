import zoneinfo
import urllib.parse
from django.utils import timezone
from django.conf import settings


class UserTimezoneMiddleware:
    """
    Middleware that dynamically activates the visitor's local regional timezone
    for the duration of each HTTP request.

    Resolution Hierarchy:
    1. Authenticated User Profile custom timezone preference (if present)
    2. 'user_timezone' or 'django_timezone' browser cookie (e.g. 'Asia/Kolkata', 'America/New_York')
    3. Default server fallback (settings.TIME_ZONE -> 'Asia/Kolkata')
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz_name = None

        # 1. Check logged-in user profile if custom timezone preference is configured
        if request.user.is_authenticated and hasattr(request.user, "profile"):
            tz_name = getattr(request.user.profile, "timezone", None)

        # 2. Check client cookie set by browser JavaScript
        if not tz_name:
            raw_cookie = request.COOKIES.get("user_timezone") or request.COOKIES.get("django_timezone")
            if raw_cookie:
                tz_name = urllib.parse.unquote(raw_cookie).strip()

        # 3. Activate valid timezone or fallback cleanly
        fallback_tz = getattr(settings, "FALLBACK_TIME_ZONE", "Asia/Kolkata")
        activated = False

        if tz_name:
            try:
                timezone.activate(zoneinfo.ZoneInfo(tz_name))
                activated = True
            except Exception:
                pass

        if not activated and fallback_tz:
            try:
                timezone.activate(zoneinfo.ZoneInfo(fallback_tz))
            except Exception:
                timezone.deactivate()

        try:
            response = self.get_response(request)
        finally:
            # 4. Clean up thread-local timezone to prevent leakage across requests
            timezone.deactivate()

        return response

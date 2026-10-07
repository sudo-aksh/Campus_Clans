from django.shortcuts import render
from django.utils import timezone


class StudentSuspensionMiddleware:
    """
    Lets a suspended student log in, but blocks normal Campus Clans pages/actions.
    Login/logout/admin/static/media paths remain available.
    Add after AuthenticationMiddleware in settings.py.
    """
    EXEMPT_PREFIXES = (
        "/login",
        "/logout",
        "/static/",
        "/media/",
        "/campus-admin/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(self.EXEMPT_PREFIXES) or not request.user.is_authenticated:
            return self.get_response(request)

        try:
            from campus_clans.models import StudentProfile
            from .models import StudentSuspension
            student = StudentProfile.objects.filter(user=request.user).first()
            if student and StudentSuspension.objects.filter(
                student=student,
                is_active=True,
                end_date__gt=timezone.now(),
            ).exists():
                return render(request, "student_suspended.html", status=403)
        except Exception:
            # Do not break the whole site if the optional admin app is being migrated.
            pass

        return self.get_response(request)

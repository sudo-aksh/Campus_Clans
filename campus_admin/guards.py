from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone


def student_is_suspended(student):
    from .models import StudentSuspension
    return StudentSuspension.objects.filter(
        student=student,
        is_active=True,
        end_date__gt=timezone.now(),
    ).exists()


def clan_is_suspended(clan):
    from .models import ClanSuspension
    return ClanSuspension.objects.filter(
        clan=clan,
        is_active=True,
        end_date__gt=timezone.now(),
    ).exists()


def block_suspended_student(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        from campus_clans.models import StudentProfile
        student = get_object_or_404(StudentProfile, user=request.user)
        if student_is_suspended(student):
            return render(request, "student_suspended.html", status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def block_suspended_clan(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        from campus_clans.models import Clan
        clan_id = kwargs.get("clan_id")
        clan = get_object_or_404(Clan, id=clan_id)
        if clan_is_suspended(clan):
            return render(request, "clan_suspended.html", {"clan": clan}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

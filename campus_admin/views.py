import json
import os
import subprocess
from datetime import timedelta

from django import forms
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.forms import modelform_factory
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from campus_clans.models import (
    Clan,
    ClanMember,
    ClanPost,
    ClanPostImage,
    ClanStory,
    ClanProject,
    ClanRecruitment,
    StudentProfile,
    StudentProject,
)

from .models import (
    AdminAction,
    AdminMessage,
    ClanAdminMessage,
    ClanEventApplication,
    ClanMembershipHistory,
    ClanMessage,
    ClanSuspension,
    DeletedClanRecord,
    DeletedStudentRecord,
    Event,
    EventClanParticipant,
    EventMedia,
    EventParticipation,
    EventTrophy,
    StudentSuspension,
)

VIDEO_MAX_BYTES = 50 * 1024 * 1024
VIDEO_MAX_SECONDS = 60

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".webm",
    ".avi",
    ".mkv",
}


# =============================================================================
# ADMIN HELPERS
# =============================================================================


def admin_required(request):
    return bool(request.session.get("is_admin"))


def admin_redirect(request):
    if not admin_required(request):
        return redirect("login")
    return None


def log_action(action, target_type, target_id, description):
    return AdminAction.objects.create(
        action=action,
        target_type=target_type,
        target_id=target_id,
        description=description,
    )


def delete_media_file(field_file):
    if not field_file:
        return

    try:
        path = field_file.path

        if os.path.isfile(path):
            os.remove(path)

    except (ValueError, OSError):
        pass


def delete_clan_media(clan):
    delete_media_file(getattr(clan, "logo", None))
    delete_media_file(getattr(clan, "banner", None))

    for post in ClanPost.objects.filter(clan=clan).prefetch_related("images"):
        for image in post.images.all():
            delete_media_file(image.image)

        delete_media_file(post.video)

    for story in ClanStory.objects.filter(clan=clan):
        delete_media_file(getattr(story, "image", None))
        delete_media_file(getattr(story, "video", None))


def student_is_suspended(student):
    return StudentSuspension.objects.filter(
        student=student,
        is_active=True,
        end_date__gt=timezone.now(),
    ).exists()


def clan_is_suspended(clan):
    return ClanSuspension.objects.filter(
        clan=clan,
        is_active=True,
        end_date__gt=timezone.now(),
    ).exists()


def parse_admin_datetime(value):
    if not value:
        return None

    value = value.strip()

    parsed = parse_datetime(value)

    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)

    return parsed


def video_duration_seconds(uploaded_file):
    """
    Return video duration using ffprobe.

    Returns None when duration cannot be verified.
    """

    try:
        uploaded_file.seek(0)

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                "-i",
                "pipe:0",
            ],
            input=uploaded_file.read(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )

        uploaded_file.seek(0)

        value = result.stdout.decode().strip()

        return float(value) if value else None

    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return None


def validate_media(uploaded_file, required_type=None):
    if not uploaded_file:
        return "No file supplied."

    name = uploaded_file.name.lower()
    ext = os.path.splitext(name)[1]

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()

    is_video = ext in VIDEO_EXTENSIONS or content_type.startswith("video/")

    is_image = ext in IMAGE_EXTENSIONS or content_type.startswith("image/")

    if required_type == "video" and not is_video:
        return "Please upload a valid video file."

    if required_type == "image" and not is_image:
        return "Please upload a valid image file."

    if not is_video and not is_image:
        return "Only image and video files are allowed."

    if is_video:

        if uploaded_file.size > VIDEO_MAX_BYTES:
            return "Video must be 50 MB or smaller."

        duration = video_duration_seconds(uploaded_file)

        if duration is None:
            return (
                "The video duration could not be verified. "
                "Install ffmpeg/ffprobe on the server and try again."
            )

        if duration > VIDEO_MAX_SECONDS:
            return "Video must be 60 seconds or shorter."

    return None


def _active_student_ids():
    now = timezone.now()

    return StudentSuspension.objects.filter(
        is_active=True,
        end_date__gt=now,
        student__isnull=False,
    ).values_list("student_id", flat=True)


# =============================================================================
# DASHBOARD
# =============================================================================


def dashboard(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    now = timezone.now()

    total_students = StudentProfile.objects.count()

    total_clans = Clan.objects.count()

    total_students_suspended = (
        StudentSuspension.objects.filter(
            is_active=True,
            end_date__gt=now,
        )
        .values("student_id")
        .distinct()
        .count()
    )

    total_clans_suspended = (
        ClanSuspension.objects.filter(
            is_active=True,
            end_date__gt=now,
        )
        .values("clan_id")
        .distinct()
        .count()
    )

    students_without_clan = StudentProfile.objects.exclude(
        id__in=ClanMember.objects.values_list(
            "student_id",
            flat=True,
        )
    ).count()

    total_clan_projects = ClanProject.objects.count()

    total_running_clan_projects = ClanProject.objects.filter(status="ongoing").count()

    total_student_projects = StudentProject.objects.count()

    total_running_student_projects = StudentProject.objects.filter(
        status="ongoing"
    ).count()

    upcoming_events = Event.objects.filter(end_date__gte=now).count()

    active_events = Event.objects.filter(
        Q(start_date__isnull=True) | Q(start_date__lte=now),
        end_date__gte=now,
    ).count()

    participating_clans = (
        EventParticipation.objects.filter(
            participant_type="clan",
            clan__isnull=False,
        )
        .values("event", "clan")
        .distinct()
        .count()
    )

    individual_event_participants = (
        EventParticipation.objects.filter(
            participant_type="student",
            student__isnull=False,
        )
        .values("event", "student")
        .distinct()
        .count()
    )

    return render(
        request,
        "dashboard.html",
        {
            "total_students": total_students,
            "total_clans": total_clans,
            "students_without_clan": students_without_clan,
            "total_clan_projects": total_clan_projects,
            "total_running_clan_projects": total_running_clan_projects,
            "total_student_projects": total_student_projects,
            "total_running_student_projects": total_running_student_projects,
            "upcoming_events": upcoming_events,
            "active_events": active_events,
            "total_students_suspended": total_students_suspended,
            "total_clans_suspended": total_clans_suspended,
            "participating_clans": participating_clans,
            "individual_event_participants": individual_event_participants,
        },
    )


# =============================================================================
# STUDENTS
# =============================================================================


def students(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    search = request.GET.get("search", "").strip()

    qs = (
        StudentProfile.objects.select_related("user")
        .prefetch_related("clan_membership__clan")
        .order_by("-created_at")
    )

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(user__username__icontains=search)
            | Q(email__icontains=search)
        )

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))

    suspended_ids = set(_active_student_ids())

    return render(
        request,
        "students.html",
        {
            "students": page_obj,
            "page_obj": page_obj,
            "search": search,
            "suspended_ids": suspended_ids,
        },
    )


class StudentAdminForm(forms.ModelForm):

    username = forms.CharField(max_length=150)

    class Meta:
        model = StudentProfile

        fields = [
            "name",
            "department",
            "branch",
            "email",
            "about",
            "github",
            "linkedin",
            "instagram",
            "youtube",
            "profile_picture",
        ]

        widgets = {
            "about": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        self.user_instance = kwargs.pop("user_instance")

        super().__init__(*args, **kwargs)

        self.fields["username"].initial = self.user_instance.username

    def clean_username(self):
        username = self.cleaned_data["username"].strip()

        if (
            User.objects.filter(username=username)
            .exclude(pk=self.user_instance.pk)
            .exists()
        ):
            raise forms.ValidationError("That username is already in use.")

        return username

    def save(self, commit=True):
        obj = super().save(commit=commit)

        self.user_instance.username = self.cleaned_data["username"]

        self.user_instance.email = self.cleaned_data.get("email", "")

        if commit:
            self.user_instance.save(
                update_fields=[
                    "username",
                    "email",
                ]
            )

        return obj


def edit_student(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    student = get_object_or_404(
        StudentProfile.objects.select_related("user"),
        id=student_id,
    )

    old_picture = student.profile_picture

    if request.method == "POST":

        form = StudentAdminForm(
            request.POST,
            request.FILES,
            instance=student,
            user_instance=student.user,
        )

        if form.is_valid():

            if old_picture and "profile_picture" in request.FILES:
                delete_media_file(old_picture)

            form.save()

            log_action(
                "Student Profile Edited",
                "Student",
                student.id,
                f"Edited student profile: {student.name}.",
            )

            return redirect(
                "campus_admin_student_view",
                student_id=student.id,
            )

    else:

        form = StudentAdminForm(
            instance=student,
            user_instance=student.user,
        )

    return render(
        request,
        "edit_student.html",
        {
            "student": student,
            "form": form,
        },
    )


def delete_student_profile_picture(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_student_view",
            student_id=student_id,
        )

    student = get_object_or_404(
        StudentProfile,
        id=student_id,
    )

    delete_media_file(student.profile_picture)

    student.profile_picture = None

    student.save(update_fields=["profile_picture"])

    log_action(
        "Student Profile Picture Deleted",
        "Student",
        student.id,
        f"Deleted profile picture of {student.name}.",
    )

    return redirect(
        "campus_admin_student_view",
        student_id=student.id,
    )


def student_view(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    student = get_object_or_404(
        StudentProfile.objects.select_related("user"),
        id=student_id,
    )

    skills = student.student_skills.select_related(
        "skill",
        "skill__skill_type",
    ).order_by(
        "skill__skill_type__name",
        "skill__name",
    )

    highlighted_skills = skills.filter(is_highlighted=True)

    personal_projects = student.personal_projects.order_by("-created_at")

    clan_membership = getattr(
        student,
        "clan_membership",
        None,
    )

    clan_projects = (
        ClanProject.objects.filter(project_members__student=student)
        .distinct()
        .order_by("-created_at")
    )

    suspensions = student.suspensions.order_by("-start_date")

    admin_messages = AdminMessage.objects.filter(student=student).order_by(
        "-created_at"
    )

    return render(
        request,
        "student_view.html",
        {
            "student": student,
            "skills": skills,
            "highlighted_skills": highlighted_skills,
            "personal_projects": personal_projects,
            "clan_membership": clan_membership,
            "clan_projects": clan_projects,
            "suspensions": suspensions,
            "admin_messages": admin_messages,
            "is_suspended": student_is_suspended(student),
        },
    )


def send_message(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    student = get_object_or_404(
        StudentProfile.objects.select_related("user"),
        id=student_id,
    )

    if request.method == "POST":

        subject = request.POST.get(
            "subject",
            "",
        ).strip()

        message = request.POST.get(
            "message",
            "",
        ).strip()

        if subject and message:

            AdminMessage.objects.create(
                student=student,
                subject=subject,
                message=message,
            )

            log_action(
                "Student Message",
                "Student",
                student.id,
                f"Sent message to {student.name}: {subject}",
            )

            return redirect(
                "campus_admin_send_message",
                student_id=student.id,
            )

    history = AdminMessage.objects.filter(student=student).order_by("-created_at")

    return render(
        request,
        "send_message.html",
        {
            "student": student,
            "message_history": history,
        },
    )


def suspend_student(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    student = get_object_or_404(
        StudentProfile.objects.select_related("user"),
        id=student_id,
    )

    if request.method == "POST":

        try:
            days = int(
                request.POST.get(
                    "days",
                    "0",
                )
            )
        except ValueError:
            days = 0

        reason = request.POST.get(
            "reason",
            "",
        ).strip()

        if days > 0:

            StudentSuspension.objects.filter(
                student=student,
                is_active=True,
            ).update(is_active=False)

            StudentSuspension.objects.create(
                student=student,
                student_name=student.name,
                end_date=(timezone.now() + timedelta(days=days)),
                reason=reason,
            )

            log_action(
                "Student Suspension",
                "Student",
                student.id,
                (
                    f"Suspended {student.name} "
                    f"for {days} day(s). "
                    f"Reason: "
                    f"{reason or 'No reason provided'}"
                ),
            )

            return redirect(
                "campus_admin_student_view",
                student_id=student.id,
            )

    return render(
        request,
        "suspend_student.html",
        {
            "student": student,
        },
    )


def unsuspend_student(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_student_view",
            student_id=student_id,
        )

    student = get_object_or_404(
        StudentProfile,
        id=student_id,
    )

    updated = StudentSuspension.objects.filter(
        student=student,
        is_active=True,
    ).update(
        is_active=False,
        end_date=timezone.now(),
    )

    if updated:

        log_action(
            "Student Unsuspended",
            "Student",
            student.id,
            f"Unsuspended {student.name}.",
        )

    return redirect(
        "campus_admin_student_view",
        student_id=student.id,
    )


# =============================================================================
# CLANS
# =============================================================================


def clans(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    qs = (
        Clan.objects.select_related("created_by")
        .prefetch_related("members__student")
        .order_by("-created_at")
    )

    search = request.GET.get(
        "search",
        "",
    ).strip()

    if search:

        qs = qs.filter(Q(name__icontains=search) | Q(speciality__icontains=search))

    page_obj = Paginator(
        qs,
        20,
    ).get_page(request.GET.get("page"))

    suspended_ids = set(
        ClanSuspension.objects.filter(
            is_active=True,
            end_date__gt=timezone.now(),
        ).values_list(
            "clan_id",
            flat=True,
        )
    )

    return render(
        request,
        "clans.html",
        {
            "clans": page_obj,
            "page_obj": page_obj,
            "search": search,
            "suspended_ids": suspended_ids,
        },
    )


class ClanAdminForm(forms.ModelForm):

    class Meta:
        model = Clan

        fields = [
            "name",
            "logo",
            "banner",
            "speciality",
            "profile_description",
            "description",
        ]

        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "profile_description": forms.Textarea(attrs={"rows": 2}),
        }


def edit_clan(request, clan_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    old_logo = clan.logo
    old_banner = clan.banner

    if request.method == "POST":

        form = ClanAdminForm(
            request.POST,
            request.FILES,
            instance=clan,
        )

        if form.is_valid():

            if old_logo and "logo" in request.FILES:
                delete_media_file(old_logo)

            if old_banner and "banner" in request.FILES:
                delete_media_file(old_banner)

            form.save()

            log_action(
                "Clan Edited",
                "Clan",
                clan.id,
                f"Edited clan: {clan.name}.",
            )

            return redirect(
                "campus_admin_clan_view",
                clan_id=clan.id,
            )

    else:

        form = ClanAdminForm(instance=clan)

    return render(
        request,
        "edit_clan.html",
        {
            "clan": clan,
            "form": form,
        },
    )


def clan_view(request, clan_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    members = (
        ClanMember.objects.filter(clan=clan)
        .select_related(
            "student",
            "student__user",
        )
        .order_by(
            "role",
            "student__name",
        )
    )

    projects = ClanProject.objects.filter(clan=clan).order_by("-created_at")

    recruitments = ClanRecruitment.objects.filter(clan=clan).order_by("-created_at")

    posts = (
        ClanPost.objects.filter(clan=clan)
        .select_related(
            "author",
            "author__user",
        )
        .prefetch_related(
            "images",
            "likes",
        )
        .order_by("-created_at")
    )

    stories = ClanStory.objects.filter(clan=clan).order_by("-created_at")

    clan_messages = ClanMessage.objects.filter(clan=clan).order_by("-created_at")

    admin_messages = ClanAdminMessage.objects.filter(clan=clan).order_by("-created_at")

    return render(
        request,
        "clan_view.html",
        {
            "clan": clan,
            "members": members,
            "projects": projects,
            "recruitments": recruitments,
            "posts": posts,
            "stories": stories,
            "clan_messages": clan_messages,
            "admin_messages": admin_messages,
            "is_suspended": clan_is_suspended(clan),
        },
    )


def remove_clan_member(request, clan_id, member_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    member = get_object_or_404(
        ClanMember.objects.select_related("student"),
        id=member_id,
        clan=clan,
    )

    if member.role == "leader":

        replacement = (
            ClanMember.objects.filter(
                clan=clan,
                role="co_leader",
            )
            .exclude(pk=member.pk)
            .order_by("joined_at")
            .first()
        )

        if replacement is None:

            replacement = (
                ClanMember.objects.filter(clan=clan)
                .exclude(pk=member.pk)
                .order_by("joined_at")
                .first()
            )

        if replacement is None:

            return redirect(
                "campus_admin_clan_view",
                clan_id=clan.id,
            )

        replacement.role = "leader"

        replacement.save(update_fields=["role"])

        clan.created_by = replacement.student

        clan.save(update_fields=["created_by"])

    ClanMembershipHistory.objects.filter(
        clan=clan,
        student=member.student,
        left_at__isnull=True,
    ).update(left_at=timezone.now())

    student_name = member.student.name

    member.delete()

    log_action(
        "Clan Member Removed",
        "Clan",
        clan.id,
        f"Removed {student_name} from {clan.name}.",
    )

    return redirect(
        "campus_admin_clan_view",
        clan_id=clan.id,
    )


def suspend_clan(request, clan_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    if request.method == "POST":

        try:
            days = int(
                request.POST.get(
                    "days",
                    "0",
                )
            )
        except ValueError:
            days = 0

        reason = request.POST.get(
            "reason",
            "",
        ).strip()

        if days > 0:

            ClanSuspension.objects.filter(
                clan=clan,
                is_active=True,
            ).update(is_active=False)

            ClanSuspension.objects.create(
                clan=clan,
                clan_name=clan.name,
                end_date=(timezone.now() + timedelta(days=days)),
                reason=reason,
            )

            log_action(
                "Clan Suspension",
                "Clan",
                clan.id,
                (
                    f"Suspended {clan.name} "
                    f"for {days} day(s). "
                    f"Reason: "
                    f"{reason or 'No reason provided'}"
                ),
            )

            return redirect(
                "campus_admin_clan_view",
                clan_id=clan.id,
            )

    return render(
        request,
        "suspend_clan.html",
        {
            "clan": clan,
        },
    )


def unsuspend_clan(request, clan_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    updated = ClanSuspension.objects.filter(
        clan=clan,
        is_active=True,
    ).update(
        is_active=False,
        end_date=timezone.now(),
    )

    if updated:

        log_action(
            "Clan Unsuspended",
            "Clan",
            clan.id,
            f"Unsuspended {clan.name}.",
        )

    return redirect(
        "campus_admin_clan_view",
        clan_id=clan.id,
    )


def message_clan(request, clan_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    if request.method == "POST":

        subject = request.POST.get(
            "subject",
            "",
        ).strip()

        message = request.POST.get(
            "message",
            "",
        ).strip()

        if subject and message:

            ClanAdminMessage.objects.create(
                clan=clan,
                subject=subject,
                message=message,
            )

            ClanMessage.objects.create(
                clan=clan,
                subject=subject,
                message=message,
                is_admin_message=True,
            )

            log_action(
                "Clan Message",
                "Clan",
                clan.id,
                (f"Sent admin message to all " f"members of {clan.name}: {subject}"),
            )

            return redirect(
                "campus_admin_message_clan",
                clan_id=clan.id,
            )

    history = ClanAdminMessage.objects.filter(clan=clan).order_by("-created_at")

    return render(
        request,
        "message_clan.html",
        {
            "clan": clan,
            "message_history": history,
        },
    )


# =============================================================================
# ADMIN CLAN POSTS / STORIES
# =============================================================================


def edit_clan_post_admin(request, clan_id, post_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    post = get_object_or_404(
        ClanPost.objects.prefetch_related("images"),
        id=post_id,
        clan=clan,
    )

    if request.method == "POST":

        content = request.POST.get(
            "content",
            "",
        ).strip()

        text = request.POST.get(
            "text",
            "",
        ).strip()

        new_files = request.FILES.getlist("media")

        remove_ids = {
            int(x) for x in request.POST.getlist("remove_images") if x.isdigit()
        }

        remove_video = request.POST.get("remove_video") == "1"

        remaining_images = post.images.exclude(id__in=remove_ids).exists()

        has_video = (bool(post.video) and not remove_video) or any(
            validate_media(
                f,
                "video",
            )
            is None
            and (
                (
                    getattr(
                        f,
                        "content_type",
                        "",
                    )
                    or ""
                ).startswith("video/")
                or os.path.splitext(f.name.lower())[1] in VIDEO_EXTENSIONS
            )
            for f in new_files
        )

        has_new_image = any(
            validate_media(
                f,
                "image",
            )
            is None
            for f in new_files
        )

        if (
            not content
            and not text
            and not remaining_images
            and not has_video
            and not has_new_image
        ):

            return render(
                request,
                "edit_clan_post.html",
                {
                    "post": post,
                    "error": (
                        "Post cannot be empty. " "Add text, an image, " "or a video."
                    ),
                },
            )

        if remove_video and post.video:

            delete_media_file(post.video)

            post.video = None

        for upload in new_files:

            error = validate_media(upload)

            if error:

                return render(
                    request,
                    "edit_clan_post.html",
                    {
                        "post": post,
                        "error": error,
                    },
                )

            is_video = (
                getattr(
                    upload,
                    "content_type",
                    "",
                )
                or ""
            ).startswith(
                "video/"
            ) or os.path.splitext(upload.name.lower())[1] in VIDEO_EXTENSIONS

            if is_video:

                if post.video:
                    delete_media_file(post.video)

                post.video = upload

            else:

                ClanPostImage.objects.create(
                    post=post,
                    image=upload,
                )

        for image in post.images.filter(id__in=remove_ids):

            delete_media_file(image.image)

            image.delete()

        post.content = content
        post.text = text

        post.save(
            update_fields=[
                "content",
                "text",
                "video",
            ]
        )

        log_action(
            "Clan Post Edited",
            "Clan Post",
            post.id,
            (f"Admin edited post #{post.id} " f"in clan {clan.name}."),
        )

        return redirect(
            "campus_admin_clan_view",
            clan_id=clan.id,
        )

    return render(
        request,
        "edit_clan_post.html",
        {
            "post": post,
        },
    )


def delete_clan_post_admin(request, clan_id, post_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    post = get_object_or_404(
        ClanPost.objects.prefetch_related("images"),
        id=post_id,
        clan=clan,
    )

    for image in post.images.all():
        delete_media_file(image.image)

    delete_media_file(post.video)

    post.delete()

    log_action(
        "Clan Post Deleted",
        "Clan Post",
        post_id,
        (f"Deleted post #{post_id} " f"from clan {clan.name}."),
    )

    return redirect(
        "campus_admin_clan_view",
        clan_id=clan.id,
    )


def delete_clan_story_admin(request, clan_id, story_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    story = get_object_or_404(
        ClanStory,
        id=story_id,
        clan=clan,
    )

    delete_media_file(getattr(story, "image", None))

    delete_media_file(getattr(story, "video", None))

    story.delete()

    log_action(
        "Clan Story Deleted",
        "Clan Story",
        story_id,
        (f"Deleted story #{story_id} " f"from clan {clan.name}."),
    )

    return redirect(
        "campus_admin_clan_view",
        clan_id=clan.id,
    )


def delete_clan(request, clan_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    DeletedClanRecord.objects.create(
        name=clan.name,
        speciality=clan.speciality,
        description=clan.description,
        created_by_name=(clan.created_by.name if clan.created_by else ""),
        original_created_at=clan.created_at,
    )

    ClanMembershipHistory.objects.filter(
        clan=clan,
        left_at__isnull=True,
    ).update(left_at=timezone.now())

    delete_clan_media(clan)

    name = clan.name

    clan.delete()

    log_action(
        "Clan Deleted",
        "Clan",
        clan_id,
        f"Deleted clan: {name}.",
    )

    return redirect("campus_admin_clans")


# =============================================================================
# CLAN PROJECTS / RECRUITMENTS
# =============================================================================


def _dynamic_model_form(
    model,
    instance=None,
    request=None,
):
    excluded = {
        "clan",
        "created_by",
        "created_at",
        "updated_at",
    }

    fields = [
        f.name
        for f in model._meta.fields
        if f.name not in excluded and not f.auto_created
    ]

    return modelform_factory(
        model,
        fields=fields,
    )(
        request.POST or None,
        request.FILES or None,
        instance=instance,
    )


def clan_project_manage(
    request,
    clan_id,
    project_id=None,
):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    project = (
        get_object_or_404(
            ClanProject,
            id=project_id,
            clan=clan,
        )
        if project_id
        else None
    )

    form = _dynamic_model_form(
        ClanProject,
        project,
        request if request.method == "POST" else None,
    )

    if request.method == "POST" and form.is_valid():

        obj = form.save(commit=False)

        obj.clan = clan

        obj.save()

        log_action(
            ("Clan Project Edited" if project else "Clan Project Created"),
            "Clan Project",
            obj.id,
            (f"Admin managed project " f"'{obj}' in {clan.name}."),
        )

        return redirect(
            "campus_admin_clan_view",
            clan_id=clan.id,
        )

    return render(
        request,
        "generic_form.html",
        {
            "form": form,
            "title": ("Edit Clan Project" if project else "Create Clan Project"),
            "back_href": reverse(
                "campus_admin_clan_view",
                args=[clan.id],
            ),
        },
    )


def delete_clan_project(
    request,
    clan_id,
    project_id,
):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    project = get_object_or_404(
        ClanProject,
        id=project_id,
        clan=clan,
    )

    project_name = str(project)

    project.delete()

    log_action(
        "Clan Project Deleted",
        "Clan Project",
        project_id,
        (f"Deleted project " f"'{project_name}' " f"from {clan.name}."),
    )

    return redirect(
        "campus_admin_clan_view",
        clan_id=clan.id,
    )


def clan_recruitment_manage(
    request,
    clan_id,
    recruitment_id=None,
):
    denied = admin_redirect(request)

    if denied:
        return denied

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    recruitment = (
        get_object_or_404(
            ClanRecruitment,
            id=recruitment_id,
            clan=clan,
        )
        if recruitment_id
        else None
    )

    form = _dynamic_model_form(
        ClanRecruitment,
        recruitment,
        request if request.method == "POST" else None,
    )

    if request.method == "POST" and form.is_valid():

        obj = form.save(commit=False)

        obj.clan = clan

        obj.save()

        log_action(
            ("Clan Recruitment Edited" if recruitment else "Clan Recruitment Created"),
            "Clan Recruitment",
            obj.id,
            (f"Admin managed recruitment " f"'{obj}' in {clan.name}."),
        )

        return redirect(
            "campus_admin_clan_view",
            clan_id=clan.id,
        )

    return render(
        request,
        "generic_form.html",
        {
            "form": form,
            "title": (
                "Edit Clan Recruitment" if recruitment else "Create Clan Recruitment"
            ),
            "back_href": reverse(
                "campus_admin_clan_view",
                args=[clan.id],
            ),
        },
    )


def delete_clan_recruitment(
    request,
    clan_id,
    recruitment_id,
):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_clan_view",
            clan_id=clan_id,
        )

    clan = get_object_or_404(
        Clan,
        id=clan_id,
    )

    recruitment = get_object_or_404(
        ClanRecruitment,
        id=recruitment_id,
        clan=clan,
    )

    title = str(recruitment)

    recruitment.delete()

    log_action(
        "Clan Recruitment Deleted",
        "Clan Recruitment",
        recruitment_id,
        (f"Deleted recruitment " f"'{title}' " f"from {clan.name}."),
    )

    return redirect(
        "campus_admin_clan_view",
        clan_id=clan.id,
    )


# =============================================================================
# EVENTS
# =============================================================================


def events(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    qs = (
        Event.objects.annotate(
            participant_count=Count(
                "participations",
                distinct=True,
            ),
            clan_participant_count=Count(
                "participations",
                filter=Q(participations__participant_type="clan"),
                distinct=True,
            ),
            student_participant_count=Count(
                "participations",
                filter=Q(participations__participant_type="student"),
                distinct=True,
            ),
        )
        .prefetch_related(
            "media",
            "trophies__clan",
        )
        .order_by("-end_date")
    )

    return render(
        request,
        "events.html",
        {
            "events": qs,
            "now": timezone.now(),
        },
    )


def _save_event_media(event, uploads):
    errors = []

    for upload in uploads:

        error = validate_media(upload)

        if error:
            errors.append(f"{upload.name}: {error}")
            continue

        is_video = (
            getattr(
                upload,
                "content_type",
                "",
            )
            or ""
        ).startswith(
            "video/"
        ) or os.path.splitext(upload.name.lower())[1] in VIDEO_EXTENSIONS

        media = EventMedia.objects.create(
            event=event,
            file=upload,
            media_type=("video" if is_video else "image"),
        )

        if not is_video and not event.image:

            event.image.name = media.file.name

            event.save(update_fields=["image"])

    return errors


def create_event(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    errors = []

    if request.method == "POST":

        name = request.POST.get(
            "name",
            "",
        ).strip()

        description = request.POST.get(
            "description",
            "",
        ).strip()

        link = request.POST.get(
            "link",
            "",
        ).strip()

        participant_type = request.POST.get(
            "participant_type",
            "clan",
        ).strip()

        if participant_type not in {
            "clan",
            "student",
            "both",
        }:
            errors.append("Invalid participant type.")

        start_date = parse_admin_datetime(request.POST.get("start_date"))

        end_date = parse_admin_datetime(request.POST.get("end_date"))

        uploads = request.FILES.getlist("media")

        if not name:
            errors.append("Event name is required.")

        if not description:
            errors.append("Event description is required.")

        if not end_date:
            errors.append("Event end date is required.")

        if start_date and end_date and start_date >= end_date:
            errors.append("Start date must be before end date.")

        for upload in uploads:

            media_error = validate_media(upload)

            if media_error:
                errors.append(f"{upload.name}: {media_error}")

        if not errors:

            event = Event.objects.create(
                name=name,
                description=description,
                link=link,
                start_date=start_date,
                end_date=end_date,
                participant_type=participant_type,
            )

            media_errors = _save_event_media(
                event,
                uploads,
            )

            if media_errors:

                errors.extend(media_errors)

                for media in event.media.all():
                    delete_media_file(media.file)

                delete_media_file(event.image)

                event.delete()

            else:

                log_action(
                    "Event Created",
                    "Event",
                    event.id,
                    f"Created event: {event.name}",
                )

                return redirect("campus_admin_events")

    return render(
        request,
        "create_event.html",
        {
            "errors": errors,
        },
    )


def edit_event(request, event_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    event = get_object_or_404(
        Event,
        id=event_id,
    )

    # Backend protection:
    # Event cannot be edited once it has ended.
    if timezone.now() >= event.end_date:
        return redirect("campus_admin_events")

    errors = []

    if request.method == "POST":

        name = request.POST.get(
            "name",
            "",
        ).strip()

        description = request.POST.get(
            "description",
            "",
        ).strip()

        link = request.POST.get(
            "link",
            "",
        ).strip()

        participant_type = request.POST.get(
            "participant_type",
            "clan",
        ).strip()

        start_date = parse_admin_datetime(request.POST.get("start_date"))

        end_date = parse_admin_datetime(request.POST.get("end_date"))

        uploads = request.FILES.getlist("media")

        remove_ids = {
            int(x) for x in request.POST.getlist("remove_media") if x.isdigit()
        }

        if participant_type not in {
            "clan",
            "student",
            "both",
        }:
            errors.append("Invalid participant type.")

        if not name:
            errors.append("Event name is required.")

        if not description:
            errors.append("Event description is required.")

        if not end_date:
            errors.append("Event end date is required.")

        if start_date and end_date and start_date >= end_date:
            errors.append("Start date must be before end date.")

        # The event must still be active
        # under the NEW submitted end date.
        if end_date and timezone.now() >= end_date:
            errors.append("Event end date must be in the future.")

        for upload in uploads:

            media_error = validate_media(upload)

            if media_error:
                errors.append(f"{upload.name}: {media_error}")

        if not errors:

            event.name = name
            event.description = description
            event.link = link
            event.start_date = start_date
            event.end_date = end_date
            event.participant_type = participant_type

            event.save()

            for media in event.media.filter(id__in=remove_ids):

                delete_media_file(media.file)

                media.delete()

            media_errors = _save_event_media(
                event,
                uploads,
            )

            if media_errors:
                errors.extend(media_errors)

            first_image = event.media.filter(media_type="image").first()

            if first_image:
                event.image = first_image.file.name
            else:
                event.image = None

            event.save(
                update_fields=[
                    "name",
                    "description",
                    "link",
                    "start_date",
                    "end_date",
                    "participant_type",
                    "image",
                ]
            )

            if not media_errors:

                log_action(
                    "Event Edited",
                    "Event",
                    event.id,
                    f"Edited event: {event.name}",
                )

                return redirect("campus_admin_events")

    return render(
        request,
        "edit_event.html",
        {
            "event": event,
            "errors": errors,
        },
    )

def event_applications(request, event_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    event = get_object_or_404(
        Event,
        id=event_id,
    )

    participations = (
        EventParticipation.objects
        .filter(event=event)
        .select_related(
            "clan",
            "student",
            "student__user",
        )
        .prefetch_related(
            "selected_members__student",
            "selected_members__student__user",
        )
        .order_by("-participated_at")
    )

    # Kept for compatibility with old data.
    # New events use EventParticipation directly.
    applications = (
        ClanEventApplication.objects
        .filter(event=event)
        .select_related("clan")
        .order_by("-applied_at")
    )

    clan_participations = participations.filter(
        participant_type="clan"
    )

    student_participations = participations.filter(
        participant_type="student"
    )

    # Add representative information for every clan participation.
    for participation in clan_participations:
        participation.representatives = [
            selected.student
            for selected in participation.selected_members.all()
        ]

    return render(
        request,
        "event_applications.html",
        {
            "event": event,
            "participations": participations,
            "clan_participations": clan_participations,
            "student_participations": student_participations,
            "applications": applications,
            "now": timezone.now(),
        },
    )

# =============================================================================
# EVENT TROPHIES
# =============================================================================
def manage_event_trophy(request, event_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    event = get_object_or_404(
        Event,
        id=event_id,
    )

    now = timezone.now()
    deadline = event.trophy_deadline

    # ---------------------------------
    # GET ALL EVENT PARTICIPATIONS
    # ---------------------------------

    participations = (
        EventParticipation.objects
        .filter(event=event)
        .select_related(
            "clan",
            "student",
            "student__user",
        )
        .prefetch_related(
            "selected_members__student",
            "selected_members__student__user",
        )
        .order_by("-participated_at")
    )

    clan_participations = participations.filter(
        participant_type="clan"
    )

    student_participations = participations.filter(
        participant_type="student"
    )

    # ---------------------------------
    # HANDLE TROPHY AWARD
    # ---------------------------------

    errors = []

    if request.method == "POST":

        # ---------------------------------
        # TROPHY WINDOW CHECK
        # ---------------------------------

        if not event.trophy_window_open:
            errors.append(
                "The 48-hour trophy window is closed."
            )

        recipient_type = request.POST.get(
            "recipient_type"
        )

        clan_id = request.POST.get(
            "clan_id"
        )

        student_id = request.POST.get(
            "student_id"
        )

        award_name = request.POST.get(
            "award_name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        # ---------------------------------
        # BASIC VALIDATION
        # ---------------------------------

        if recipient_type not in ["clan", "student"]:
            errors.append(
                "Please select a valid recipient type."
            )

        if not award_name:
            errors.append(
                "Award name is required."
            )

        # ---------------------------------
        # CLAN TROPHY
        # ---------------------------------

        if recipient_type == "clan":

            if not clan_id:
                errors.append(
                    "Please select a participating clan."
                )

            else:

                clan_participation = (
                    EventParticipation.objects
                    .filter(
                        event=event,
                        participant_type="clan",
                        clan_id=clan_id,
                    )
                    .select_related("clan")
                    .first()
                )

                if not clan_participation:
                    errors.append(
                        "That clan did not participate in this event."
                    )

                else:

                    clan = clan_participation.clan

                    # Prevent duplicate same award
                    duplicate = EventTrophy.objects.filter(
                        event=event,
                        clan=clan,
                        award_name=award_name,
                    ).exists()

                    if duplicate:
                        errors.append(
                            "This clan already has this trophy."
                        )

        # ---------------------------------
        # STUDENT TROPHY
        # ---------------------------------

        elif recipient_type == "student":

            if not student_id:
                errors.append(
                    "Please select a participating student."
                )

            else:

                student_participation = (
                    EventParticipation.objects
                    .filter(
                        event=event,
                        participant_type="student",
                        student_id=student_id,
                    )
                    .select_related(
                        "student",
                        "student__user",
                    )
                    .first()
                )

                if not student_participation:
                    errors.append(
                        "That student did not participate in this event."
                    )

                else:

                    student = student_participation.student

                    # Prevent duplicate same award
                    duplicate = EventTrophy.objects.filter(
                        event=event,
                        student=student,
                        award_name=award_name,
                    ).exists()

                    if duplicate:
                        errors.append(
                            "This student already has this trophy."
                        )

        # ---------------------------------
        # CREATE TROPHY
        # ---------------------------------

        if not errors:

            if recipient_type == "clan":

                EventTrophy.objects.create(
                    event=event,
                    clan=clan,
                    student=None,
                    award_name=award_name,
                    description=description,
                )

            else:

                EventTrophy.objects.create(
                    event=event,
                    clan=None,
                    student=student,
                    award_name=award_name,
                    description=description,
                )

            return redirect(
                "campus_admin_manage_event_trophy",
                event_id=event.id,
            )

    # ---------------------------------
    # EXISTING TROPHIES
    # ---------------------------------

    trophies = (
        EventTrophy.objects
        .filter(event=event)
        .select_related(
            "clan",
            "student",
            "student__user",
        )
        .prefetch_related(
            "event__participations__selected_members__student"
        )
        .order_by("-awarded_at")
    )


    # ---------------------------------
    # PAGE
    # ---------------------------------

    return render(
        request,
        "event_trophies.html",
        {
            "event": event,
            "participations": participations,
            "clan_participations": clan_participations,
            "student_participations": student_participations,
            "trophies": trophies,
            "deadline": deadline,
            "errors": errors,
            "now": now,
        },
    )

def delete_event_trophy(
    request,
    event_id,
    trophy_id,
):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect(
            "campus_admin_event_trophies",
            event_id=event_id,
        )

    event = get_object_or_404(
        Event,
        id=event_id,
    )

    trophy = get_object_or_404(
        EventTrophy,
        id=trophy_id,
        event=event,
    )

    if event.trophy_window_open:

        trophy_name = trophy.award_name

        clan_name = trophy.clan.name

        trophy.delete()

        log_action(
            "Event Trophy Removed",
            "Event Trophy",
            trophy_id,
            (f"Removed '{trophy_name}' " f"from {clan_name} " f"for {event.name}."),
        )

    return redirect(
        "campus_admin_event_trophies",
        event_id=event.id,
    )


# =============================================================================
# DELETE EVENT
# =============================================================================


def delete_event(request, event_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    if request.method != "POST":
        return redirect("campus_admin_events")

    event = get_object_or_404(
        Event,
        id=event_id,
    )

    # Event cannot be deleted after it ends.
    if timezone.now() >= event.end_date:
        return redirect("campus_admin_events")

    event_name = event.name

    for media in event.media.all():
        delete_media_file(media.file)

    delete_media_file(event.image)

    event.delete()

    log_action(
        "Event Deleted",
        "Event",
        event_id,
        f"Deleted event: {event_name}",
    )

    return redirect("campus_admin_events")


# =============================================================================
# REPORTS
# =============================================================================


def reports(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    now = timezone.now()

    active_student_suspensions = (
        StudentSuspension.objects.filter(
            is_active=True,
            end_date__gt=now,
        )
        .select_related("student")
        .order_by("-start_date")
    )

    active_clan_suspensions = (
        ClanSuspension.objects.filter(
            is_active=True,
            end_date__gt=now,
        )
        .select_related("clan")
        .order_by("-start_date")
    )

    context = {
        "active_student_suspensions": (active_student_suspensions),
        "active_clan_suspensions": (active_clan_suspensions),
        "suspension_history": (
            StudentSuspension.objects.select_related("student").order_by("-start_date")[
                :100
            ]
        ),
        "clan_suspension_history": (
            ClanSuspension.objects.select_related("clan").order_by("-start_date")[:100]
        ),
        "admin_actions": (AdminAction.objects.order_by("-created_at")[:200]),
        "admin_messages": (
            AdminMessage.objects.select_related("student").order_by("-created_at")[:100]
        ),
        "clan_messages": (
            ClanMessage.objects.select_related("clan").order_by("-created_at")[:100]
        ),
        # Kept only for compatibility with the old
        # report template. New event participation
        # does not create pending applications.
        "pending_event_applications": (
            ClanEventApplication.objects.filter(status="pending").count()
        ),
        "monthly": monthly_report_data(
            now.year,
            now.month,
        ),
    }

    return render(
        request,
        "reports.html",
        context,
    )


def monthly_report_data(year, month):
    from calendar import monthrange

    start = timezone.make_aware(
        timezone.datetime(
            year,
            month,
            1,
        )
    )

    last_day = monthrange(
        year,
        month,
    )[1]

    end = timezone.make_aware(
        timezone.datetime(
            year,
            month,
            last_day,
            23,
            59,
            59,
        )
    )

    return {
        "year": year,
        "month": month,
        "students_new": (
            StudentProfile.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "students_total": (StudentProfile.objects.count()),
        "students_suspended": (
            StudentSuspension.objects.filter(
                start_date__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "students_deleted": (
            DeletedStudentRecord.objects.filter(
                deleted_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "clans_new": (
            Clan.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "clans_total": (Clan.objects.count()),
        "clans_suspended": (
            ClanSuspension.objects.filter(
                start_date__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "clans_deleted": (
            DeletedClanRecord.objects.filter(
                deleted_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "posts": (
            ClanPost.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "stories": (
            ClanStory.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "events": (
            Event.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "participations": (
            EventParticipation.objects.filter(
                participated_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "clan_participations": (
            EventParticipation.objects.filter(
                participant_type="clan",
                participated_at__range=(
                    start,
                    end,
                ),
            ).count()
        ),
        "student_participations": (
            EventParticipation.objects.filter(
                participant_type="student",
                participated_at__range=(
                    start,
                    end,
                ),
            ).count()
        ),
        "trophies": (
            EventTrophy.objects.filter(
                awarded_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "student_projects": (
            StudentProject.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "clan_projects": (
            ClanProject.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "recruitments": (
            ClanRecruitment.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
        "admin_actions": (
            AdminAction.objects.filter(
                created_at__range=(
                    start,
                    end,
                )
            ).count()
        ),
    }


def monthly_report_csv(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    import csv
    from django.http import HttpResponse

    now = timezone.now()

    data = monthly_report_data(
        now.year,
        now.month,
    )

    response = HttpResponse(content_type="text/csv")

    response["Content-Disposition"] = (
        f"attachment; filename="
        f'"campus_report_'
        f"{now.year}_"
        f'{now.month:02d}.csv"'
    )

    writer = csv.writer(response)

    writer.writerow(
        [
            "Metric",
            "Value",
        ]
    )

    for key, value in data.items():

        if key not in {
            "year",
            "month",
        }:

            writer.writerow(
                [
                    key.replace(
                        "_",
                        " ",
                    ).title(),
                    value,
                ]
            )

    return response


def monthly_report_json(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    now = timezone.now()

    return JsonResponse(
        monthly_report_data(
            now.year,
            now.month,
        )
    )


def monthly_report_excel(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    from io import BytesIO
    from openpyxl import Workbook
    from django.http import HttpResponse

    now = timezone.now()

    data = monthly_report_data(
        now.year,
        now.month,
    )

    wb = Workbook()

    ws = wb.active

    ws.title = "Monthly Report"

    ws.append(
        [
            "Metric",
            "Value",
        ]
    )

    for key, value in data.items():

        if key not in {
            "year",
            "month",
        }:

            ws.append(
                [
                    key.replace(
                        "_",
                        " ",
                    ).title(),
                    value,
                ]
            )

    output = BytesIO()

    wb.save(output)

    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/" "vnd.openxmlformats-officedocument." "spreadsheetml.sheet"
        ),
    )

    response["Content-Disposition"] = (
        f"attachment; filename="
        f'"campus_report_'
        f"{now.year}_"
        f'{now.month:02d}.xlsx"'
    )

    return response


def monthly_report_pdf(request):
    denied = admin_redirect(request)

    if denied:
        return denied

    from io import BytesIO

    from reportlab.lib.pagesizes import A4

    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    from reportlab.lib import colors

    from reportlab.lib.styles import (
        getSampleStyleSheet,
    )

    from django.http import HttpResponse

    now = timezone.now()

    data = monthly_report_data(
        now.year,
        now.month,
    )

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    story = [
        Paragraph(
            (f"Campus Monthly Report — " f"{now.strftime('%B %Y')}"),
            styles["Title"],
        ),
        Spacer(
            1,
            16,
        ),
    ]

    rows = [
        [
            "Metric",
            "Value",
        ]
    ]

    for key, value in data.items():

        if key not in {
            "year",
            "month",
        }:

            rows.append(
                [
                    key.replace(
                        "_",
                        " ",
                    ).title(),
                    str(value),
                ]
            )

    table = Table(
        rows,
        colWidths=[
            320,
            120,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "PADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
            ]
        )
    )

    story.append(table)

    doc.build(story)

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )

    response["Content-Disposition"] = (
        f"attachment; filename="
        f'"campus_report_'
        f"{now.year}_"
        f'{now.month:02d}.pdf"'
    )

    return response


# =============================================================================
# DELETE STUDENT
# =============================================================================


def delete_student(request, student_id):
    denied = admin_redirect(request)

    if denied:
        return denied

    student = get_object_or_404(
        StudentProfile.objects.select_related("user"),
        id=student_id,
    )

    if request.method == "POST":

        user = student.user

        profile_picture = student.profile_picture

        DeletedStudentRecord.objects.create(
            name=student.name,
            username=user.username,
            email=student.email,
            department=student.department,
            branch=student.branch,
            original_created_at=student.created_at,
        )

        membership = (
            ClanMember.objects.filter(student=student).select_related("clan").first()
        )

        if membership:

            ClanMembershipHistory.objects.filter(
                clan=membership.clan,
                student=student,
                left_at__isnull=True,
            ).update(left_at=timezone.now())

            # If the student is the leader,
            # promote a co-leader/member.
            if membership.role == "leader":

                replacement = (
                    ClanMember.objects.filter(clan=membership.clan)
                    .exclude(student=student)
                    .filter(role="co_leader")
                    .order_by("joined_at")
                    .first()
                )

                if replacement is None:

                    replacement = (
                        ClanMember.objects.filter(clan=membership.clan)
                        .exclude(student=student)
                        .order_by("joined_at")
                        .first()
                    )

                if replacement:

                    replacement.role = "leader"

                    replacement.save(update_fields=["role"])

                    membership.clan.created_by = replacement.student

                    membership.clan.save(update_fields=["created_by"])

                else:

                    DeletedClanRecord.objects.create(
                        name=membership.clan.name,
                        speciality=membership.clan.speciality,
                        description=membership.clan.description,
                        created_by_name=student.name,
                        original_created_at=(membership.clan.created_at),
                    )

                    delete_clan_media(membership.clan)

                    membership.clan.delete()

        log_action(
            "Student Deleted",
            "Student",
            student.id,
            (f"Deleted student account: " f"{student.name} " f"({user.username})"),
        )

        delete_media_file(profile_picture)

        user.delete()

        return redirect("campus_admin_students")

    return render(
        request,
        "delete_student.html",
        {
            "student": student,
        },
    )


# =============================================================================
# DELETE STUDENT MESSAGE
# =============================================================================


def delete_message(
    request,
    student_id,
    message_id,
):
    denied = admin_redirect(request)

    if denied:
        return denied

    student = get_object_or_404(
        StudentProfile,
        id=student_id,
    )

    message = get_object_or_404(
        AdminMessage,
        id=message_id,
        student=student,
    )

    if request.method == "POST":

        subject = message.subject

        message.delete()

        log_action(
            "Student Message Deleted",
            "Student Message",
            message_id,
            (f"Deleted message " f"'{subject}' " f"from {student.name}."),
        )

    return redirect(
        "campus_admin_send_message",
        student_id=student.id,
    )


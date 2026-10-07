import json
from django.contrib.auth import logout
from datetime import timedelta, datetime
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import (
    StudentProfile,
    Skill,
    StudentSkill,
    SkillType,
    Clan,
    ClanMember,
    ClanInvitation,
    ClanJoinRequest,
    ClanPost,
    ClanPostLike,
    ClanPostImage,
    ClanStory,
    ClanStoryView,
    ClanStoryLike,
    ClanRecruitment,
    ClanRecruitmentSkill,
    ClanLeaveRequest,
    StudentClanRecruitment,
    StudentProject,
    StudentProjectLink,
    StudentProjectImage,
    StudentProjectUpdate,
    StudentProjectUpdateImage,
    ClanProject,
    ClanProjectLink,
    ClanProjectImage,
    ClanProjectMember,
    ClanProjectUpdate,
    ClanProjectUpdateImage,
    OTPRequestLog,
    ClanProjectUpdateParticipant,
)
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
import subprocess
import random
from django.contrib import messages
import os
import secrets
from django.db import transaction
from functools import wraps
from django.db.models import Q, Count, Prefetch
from campus_admin.models import (
    StudentSuspension,
    AdminMessage,
    ClanMessage,
    Event,
    ClanEventApplication,
    ClanMembershipHistory,
    ClanSuspension,
    EventParticipation,
    EventTrophy,
    EventClanParticipant,
)

OTP_FIRST_EXPIRY_SECONDS = 180
OTP_RESEND_EXPIRY_SECONDS = 120
OTP_MAX_ATTEMPTS = 10
OTP_MAX_SENDS_24_HOURS = 10
OTP_SEND_WINDOW_SECONDS = 24 * 60 * 60


def clan_is_suspended(clan):
    return ClanSuspension.objects.filter(
        clan=clan,
        end_date__gt=timezone.now(),
    ).exists()


def _otp_send_limit(email, purpose):
    cutoff = timezone.now() - timedelta(seconds=OTP_SEND_WINDOW_SECONDS)

    return OTPRequestLog.objects.filter(
        email__iexact=email,
        purpose=purpose,
        created_at__gte=cutoff,
    ).count()


def _otp_sends_remaining(email, purpose):
    used = _otp_send_limit(email, purpose)

    return max(0, OTP_MAX_SENDS_24_HOURS - used)


def _otp_is_expired(created_at, expiry_seconds):
    if not created_at:
        return True

    try:
        return timezone.now().timestamp() - float(created_at) >= expiry_seconds
    except (TypeError, ValueError):
        return True


def delete_media_file(field_file):
    """
    Delete the physical file belonging to a Django FileField/ImageField.
    """
    if not field_file:
        return

    try:
        file_path = field_file.path

        if os.path.isfile(file_path):
            os.remove(file_path)

    except (ValueError, OSError):
        pass


def _clear_registration_otp(request):
    for key in (
        "registration_otp",
        "registration_otp_created_at",
        "registration_otp_attempts",
    ):
        request.session.pop(key, None)


def _clear_email_change_otp(request):
    for key in (
        "email_change_otp",
        "email_change_otp_created_at",
        "email_change_otp_attempts",
    ):
        request.session.pop(key, None)


def _record_membership_join(membership):
    ClanMembershipHistory.objects.create(
        clan=membership.clan,
        clan_name=membership.clan.name,
        student=membership.student,
        student_name=membership.student.name,
        role=membership.role,
        joined_at=membership.joined_at,
    )


def _record_membership_leave(membership):
    ClanMembershipHistory.objects.filter(
        clan=membership.clan,
        student=membership.student,
        left_at__isnull=True,
    ).update(left_at=timezone.now())


def _close_clan_membership_histories(clan):
    ClanMembershipHistory.objects.filter(
        clan=clan,
        left_at__isnull=True,
    ).update(left_at=timezone.now())


def check_username(request):
    username = request.GET.get("username", "").strip()

    if not username:
        return JsonResponse(
            {"available": False, "message": "Username cannot be empty."}
        )

    username_query = User.objects.filter(username__iexact=username)

    if request.user.is_authenticated:
        username_query = username_query.exclude(id=request.user.id)

    exists = username_query.exists()

    if exists:
        return JsonResponse(
            {"available": False, "message": "Username is already taken."}
        )

    return JsonResponse({"available": True, "message": "Username is available."})


def _clear_password_reset_otp(request):
    for key in (
        "password_reset_otp",
        "password_reset_otp_created_at",
        "password_reset_otp_attempts",
        "password_reset_email",
        "password_reset_user_id",
    ):
        request.session.pop(key, None)


@login_required
def global_recruitments(request):

    profile = get_object_or_404(StudentProfile, user=request.user)

    now = timezone.now()

    # Remove expired student recruitment posts
    StudentClanRecruitment.objects.filter(expires_at__lte=now).delete()

    # ---------------------------------------------------------
    # CURRENT USER'S CLAN MEMBERSHIP
    # ---------------------------------------------------------

    current_membership = (
        ClanMember.objects.select_related("clan").filter(student=profile).first()
    )

    # Leader / Co-Leader can invite students
    can_invite_students = (
        current_membership is not None
        and current_membership.role in ["leader", "co_leader"]
    )

    # ---------------------------------------------------------
    # CLAN RECRUITMENTS
    # ---------------------------------------------------------

    recruitments = (
        ClanRecruitment.objects.filter(expires_at__gt=now)
        .select_related("clan", "created_by")
        .prefetch_related("fields", "recruitment_skills__skill")
        .order_by("-created_at")
    )

    # Current student's skills
    student_skill_ids = set(
        StudentSkill.objects.filter(student=profile).values_list("skill_id", flat=True)
    )

    recruitment_data = []

    for recruitment in recruitments:

        # -----------------------------------------------------
        # SKILL MATCHING
        # -----------------------------------------------------

        required_skills = list(recruitment.recruitment_skills.all())

        required_skill_ids = {item.skill_id for item in required_skills}

        matched_skill_ids = student_skill_ids & required_skill_ids

        matched_skills = [
            item.skill for item in required_skills if item.skill_id in matched_skill_ids
        ]

        total_required = len(required_skills)

        match_count = len(matched_skills)

        match_percentage = (
            round((match_count / total_required) * 100) if total_required else 0
        )

        # -----------------------------------------------------
        # CURRENT USER'S JOIN REQUEST
        # -----------------------------------------------------

        existing_request = ClanJoinRequest.objects.filter(
            clan=recruitment.clan, student=profile, status="pending"
        ).first()

        # -----------------------------------------------------
        # CURRENT USER ALREADY A MEMBER?
        # -----------------------------------------------------

        is_member = ClanMember.objects.filter(
            clan=recruitment.clan, student=profile
        ).exists()

        # -----------------------------------------------------
        # CAN CURRENT USER MANAGE THIS RECRUITMENT?
        #
        # Only Leader / Co-Leader of THIS clan.
        # -----------------------------------------------------

        can_manage = (
            current_membership is not None
            and current_membership.clan_id == recruitment.clan_id
            and current_membership.role in ["leader", "co_leader"]
        )

        recruitment_data.append(
            {
                "recruitment": recruitment,
                "required_skills": required_skills,
                "matched_skills": matched_skills,
                "match_count": match_count,
                "total_required": total_required,
                "match_percentage": match_percentage,
                "existing_request": existing_request,
                "is_member": is_member,
                "can_manage": can_manage,
            }
        )

    # ---------------------------------------------------------
    # STUDENT RECRUITMENTS
    # ---------------------------------------------------------

    student_recruitments = (
        StudentClanRecruitment.objects.filter(expires_at__gt=now)
        .select_related("student", "student__user")
        .prefetch_related("student__student_skills__skill__skill_type")
        .order_by("-created_at")
    )

    # ---------------------------------------------------------
    # RENDER
    # ---------------------------------------------------------

    return render(
        request,
        "clans/global_recruitments.html",
        {
            "recruitments": recruitment_data,
            "student_recruitments": student_recruitments,
            "current_profile": profile,
            "current_membership": current_membership,
            "can_invite_students": can_invite_students,
        },
    )


def student_is_suspended(student):
    return StudentSuspension.objects.filter(
        student=student, end_date__gt=timezone.now()
    ).exists()

def block_suspended_student(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if request.user.is_authenticated:

            try:
                student = request.user.studentprofile
            except StudentProfile.DoesNotExist:
                return view_func(request, *args, **kwargs)

            suspension = (
                StudentSuspension.objects.filter(
                    student=student,
                    end_date__gt=timezone.now()
                )
                .order_by("-end_date")
                .first()
            )

            if suspension:

                # AJAX request
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Your account is currently suspended."
                        },
                        status=403
                    )

                # Normal browser request
                return render(
                    request,
                    "user/suspended.html",
                    {
                        "suspension": suspension
                    }
                )

        return view_func(request, *args, **kwargs)

    return wrapper


@login_required
def student_clan_recruitments(request):
    """
    Show all active student clan recruitment posts.
    """

    # Clean up expired recruitments whenever this page is opened
    StudentClanRecruitment.objects.filter(expires_at__lte=timezone.now()).delete()

    recruitments = (
        StudentClanRecruitment.objects.select_related("student", "student__user")
        .filter(expires_at__gt=timezone.now())
        .order_by("-created_at")
    )

    current_student = get_object_or_404(StudentProfile, user=request.user)

    # Student's own active recruitment
    own_recruitment = StudentClanRecruitment.objects.filter(
        student=current_student, expires_at__gt=timezone.now()
    ).first()

    return render(
        request,
        "clans/student_recruitments.html",
        {
            "recruitments": recruitments,
            "own_recruitment": own_recruitment,
            "current_student": current_student,
        },
    )


@login_required
@block_suspended_student
def create_student_clan_recruitment(request):

    student = get_object_or_404(StudentProfile, user=request.user)

    # Student cannot create recruitment if already in a clan
    if ClanMember.objects.filter(student=student).exists():
        return redirect("student_clan_recruitments")

    # Remove expired recruitment first
    StudentClanRecruitment.objects.filter(
        student=student, expires_at__lte=timezone.now()
    ).delete()

    # Only one active recruitment per student
    if StudentClanRecruitment.objects.filter(
        student=student, expires_at__gt=timezone.now()
    ).exists():
        return redirect("student_clan_recruitments")

    if request.method == "POST":

        message = request.POST.get("message", "").strip()

        if not message:
            return redirect("student_clan_recruitments")

        StudentClanRecruitment.objects.create(
            student=student,
            message=message,
            expires_at=timezone.now() + timedelta(days=7),
        )

        return redirect("student_clan_recruitments")

    return redirect("student_clan_recruitments")


@login_required
@block_suspended_student
def delete_student_project(request, project_id):

    if request.method != "POST":
        return redirect("profile")

    profile = get_object_or_404(StudentProfile, user=request.user)

    project = get_object_or_404(StudentProject, id=project_id, student=profile)

    # Delete original project images
    for project_image in project.images.all():
        if project_image.image:
            project_image.image.delete(save=False)

    # Delete all update images
    for update in project.updates.all():
        for update_image in update.images.all():
            if update_image.image:
                update_image.image.delete(save=False)

    project.delete()

    messages.success(request, "Project deleted successfully.")

    return redirect("profile")


@login_required
@block_suspended_student
def delete_student_project_update(request, update_id):

    if request.method != "POST":
        return redirect("profile")

    profile = get_object_or_404(StudentProfile, user=request.user)

    update = get_object_or_404(
        StudentProjectUpdate.objects.select_related("project"), id=update_id
    )

    # Only the project owner can delete the update
    if update.project.student_id != profile.id:
        return redirect("student_project_detail", project_id=update.project.id)

    # Delete all update images from storage
    for update_image in update.images.all():
        if update_image.image:
            update_image.image.delete(save=False)

    project_id = update.project_id

    # Delete the update record
    update.delete()

    messages.success(request, "Project update deleted successfully.")

    return redirect("student_project_detail", project_id=project_id)


@login_required
@block_suspended_student
def delete_student_clan_recruitment(request, recruitment_id):

    student = get_object_or_404(StudentProfile, user=request.user)

    recruitment = get_object_or_404(
        StudentClanRecruitment, id=recruitment_id, student=student
    )

    if request.method == "POST":
        recruitment.delete()

    return redirect("student_clan_recruitments")


@login_required
@block_suspended_student
def invite_student_to_clan(request, recruitment_id):

    student = get_object_or_404(StudentProfile, user=request.user)

    recruitment = get_object_or_404(
        StudentClanRecruitment.objects.select_related("student"),
        id=recruitment_id,
        expires_at__gt=timezone.now(),
    )

    clan_member = get_object_or_404(
        ClanMember.objects.select_related("clan"), student=student
    )

    if clan_member.role not in ["leader", "co_leader"]:
        return redirect("student_clan_recruitments")

    clan = clan_member.clan
    target_student = recruitment.student

    if target_student == student:
        return redirect("student_clan_recruitments")

    if ClanMember.objects.filter(student=target_student).exists():
        return redirect("student_clan_recruitments")

    if ClanMember.objects.filter(clan=clan).count() >= 12:
        return redirect("student_clan_recruitments")

    if ClanInvitation.objects.filter(
        clan=clan, invited_student=target_student, status="pending"
    ).exists():
        return redirect("student_clan_recruitments")

    ClanInvitation.objects.create(
        clan=clan, invited_student=target_student, invited_by=student, status="pending"
    )

    return redirect("student_clan_recruitments")


@login_required
@block_suspended_student
def send_global_clan_join_request(request, recruitment_id):

    if request.method != "POST":
        return redirect("global_recruitments")

    profile = get_object_or_404(StudentProfile, user=request.user)

    recruitment = get_object_or_404(
        ClanRecruitment, id=recruitment_id, expires_at__gt=timezone.now()
    )

    clan = recruitment.clan

    # Already a member of a clan
    existing_membership = ClanMember.objects.filter(student=profile).first()

    if existing_membership:
        return redirect("global_recruitments")

    # Check if this student already has any pending
    # join request to this clan
    existing_request = ClanJoinRequest.objects.filter(
        clan=clan, student=profile, status="pending"
    ).first()

    if existing_request:
        return redirect("global_recruitments")

    ClanJoinRequest.objects.create(
        clan=clan, student=profile, request_type="global", recruitment=recruitment
    )

    return redirect("global_recruitments")


@login_required
@block_suspended_student
def delete_clan_post(request, post_id):

    if request.method != "POST":
        return redirect("home")

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=profile).first()

    if not membership:
        return redirect("clan_posts", clan_id=post.clan_id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_posts", clan_id=post.clan_id)

    clan_id = post.clan_id

    for post_image in post.images.all():

        if post_image.image:
            post_image.image.delete(save=False)

    if post.video:
        post.video.delete(save=False)

    # Delete database object
    post.delete()

    return redirect("clan_posts", clan_id=clan_id)


@login_required
@block_suspended_student
def edit_clan_story(request, story_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory.objects.select_related("clan"), id=story_id)

    membership = ClanMember.objects.filter(clan=story.clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=story.clan_id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=story.clan_id)

    # Cannot edit expired story
    if story.expires_at <= timezone.now():
        return redirect("clan_profile", clan_id=story.clan_id)

    if request.method == "POST":

        text = request.POST.get("text", "").strip()

        new_image = request.FILES.get("image")

        new_video = request.FILES.get("video")

        # TEXT
        if story.story_type == "text":

            if not text:
                return render(
                    request,
                    "clans/edit_story.html",
                    {"story": story, "error": "Text story cannot be empty."},
                )

            story.text = text

        # IMAGE
        elif story.story_type == "image":

            if new_image:

                if story.image:
                    story.image.delete(save=False)

                story.image = new_image

        # VIDEO
        elif story.story_type == "video":

            if new_video:

                if story.video:
                    story.video.delete(save=False)

                story.video = new_video

        story.save()

        return redirect("view_clan_story", story_id=story.id)

    return render(request, "clans/edit_story.html", {"story": story})


@login_required
@block_suspended_student
def edit_clan_recruitment(request, recruitment_id):
    profile = get_object_or_404(StudentProfile, user=request.user)
    recruitment = get_object_or_404(
        ClanRecruitment.objects.select_related("clan", "created_by"), id=recruitment_id
    )
    clan = recruitment.clan
    membership = ClanMember.objects.filter(clan=clan, student=profile).first()
    if not membership:
        return redirect("clan_profile", clan_id=clan.id)
    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)
    if recruitment.expires_at <= timezone.now():
        return redirect("clan_profile", clan_id=clan.id)
    skill_types = SkillType.objects.all()
    selected_field_ids = set(recruitment.fields.values_list("id", flat=True))
    selected_skill_ids = set(
        recruitment.required_skills.values_list("skill_id", flat=True)
    )
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        field_ids = request.POST.getlist("fields")
        skill_ids = list(dict.fromkeys(request.POST.getlist("skills")))
        if not title:
            return render(
                request,
                "clans/edit_recruitment.html",
                {
                    "clan": clan,
                    "recruitment": recruitment,
                    "skill_types": skill_types,
                    "selected_field_ids": set(field_ids),
                    "selected_skill_ids": set(skill_ids),
                    "error": "Recruitment title is required.",
                },
            )
        if not field_ids:
            return render(
                request,
                "clans/edit_recruitment.html",
                {
                    "clan": clan,
                    "recruitment": recruitment,
                    "skill_types": skill_types,
                    "selected_field_ids": set(field_ids),
                    "selected_skill_ids": set(skill_ids),
                    "error": "Please select at least one field.",
                },
            )
        if not skill_ids:
            return render(
                request,
                "clans/edit_recruitment.html",
                {
                    "clan": clan,
                    "recruitment": recruitment,
                    "skill_types": skill_types,
                    "selected_field_ids": set(field_ids),
                    "selected_skill_ids": set(skill_ids),
                    "error": "Please select at least one required skill.",
                },
            )
        if len(skill_ids) > 35:
            return render(
                request,
                "clans/edit_recruitment.html",
                {
                    "clan": clan,
                    "recruitment": recruitment,
                    "skill_types": skill_types,
                    "selected_field_ids": set(field_ids),
                    "selected_skill_ids": set(skill_ids),
                    "error": "You can select a maximum of 35 skills.",
                },
            )
        fields = SkillType.objects.filter(id__in=field_ids)
        if fields.count() != len(set(field_ids)):
            return render(
                request,
                "clans/edit_recruitment.html",
                {
                    "clan": clan,
                    "recruitment": recruitment,
                    "skill_types": skill_types,
                    "selected_field_ids": set(field_ids),
                    "selected_skill_ids": set(skill_ids),
                    "error": "Invalid field selection.",
                },
            )
        skills = Skill.objects.filter(id__in=skill_ids)
        if skills.count() != len(set(skill_ids)):
            return render(
                request,
                "clans/edit_recruitment.html",
                {
                    "clan": clan,
                    "recruitment": recruitment,
                    "skill_types": skill_types,
                    "selected_field_ids": set(field_ids),
                    "selected_skill_ids": set(skill_ids),
                    "error": "Invalid skill selection.",
                },
            )
        recruitment.title = title
        recruitment.description = description
        recruitment.save(
            update_fields=[
                "title",
                "description",
            ]
        )
        recruitment.fields.set(fields)
        ClanRecruitmentSkill.objects.filter(recruitment=recruitment).delete()
        ClanRecruitmentSkill.objects.bulk_create(
            [
                ClanRecruitmentSkill(recruitment=recruitment, skill=skill)
                for skill in skills
            ]
        )
        return redirect("clan_profile", clan_id=clan.id)
    return render(
        request,
        "clans/edit_recruitment.html",
        {
            "clan": clan,
            "recruitment": recruitment,
            "skill_types": skill_types,
            "selected_field_ids": selected_field_ids,
            "selected_skill_ids": selected_skill_ids,
        },
    )


@login_required
@block_suspended_student
def delete_clan_recruitment(request, recruitment_id):
    if request.method != "POST":
        return redirect("home")
    profile = get_object_or_404(StudentProfile, user=request.user)
    recruitment = get_object_or_404(
        ClanRecruitment.objects.select_related("clan"), id=recruitment_id
    )
    clan = recruitment.clan
    membership = ClanMember.objects.filter(clan=clan, student=profile).first()
    if not membership:
        return redirect("clan_profile", clan_id=clan.id)
    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)
    recruitment.delete()
    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def edit_clan_post(request, post_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=profile).first()

    # Only clan members can manage posts
    if not membership:
        return redirect("clan_posts", clan_id=post.clan_id)

    # Only leader and co-leader can edit
    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_posts", clan_id=post.clan_id)

    # At exactly 7 days, editing is no longer allowed.
    if timezone.now() >= post.created_at + timedelta(days=7):
        return redirect("clan_posts", clan_id=post.clan_id)

    if request.method == "POST":

        content = request.POST.get("content", "").strip()

        existing_images = post.images.exists()
        existing_video = bool(post.video)

        if not content and not existing_images and not existing_video:
            return render(
                request,
                "clans/edit_post.html",
                {
                    "post": post,
                    "error": "Post cannot be empty. Add text, an image, or a video.",
                },
            )

        post.content = content

        post.save(update_fields=["content"])

        return redirect("clan_posts", clan_id=post.clan_id)

    return render(request, "clans/edit_post.html", {"post": post})


@login_required
@block_suspended_student
def create_clan_story_page(request, clan_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=clan.id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)

    return render(request, "clans/create_story.html", {"clan": clan})


@login_required
@block_suspended_student
def delete_clan_story(request, story_id):

    if request.method != "POST":
        return redirect("home")

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory.objects.select_related("clan"), id=story_id)

    membership = ClanMember.objects.filter(clan=story.clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=story.clan_id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=story.clan_id)

    clan_id = story.clan_id

    # Delete physical image
    if story.image:
        story.image.delete(save=False)

    # Delete physical video
    if story.video:
        story.video.delete(save=False)

    story.delete()

    return redirect("clan_profile", clan_id=clan_id)


@login_required
@block_suspended_student
def create_clan_recruitment(request, clan_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=clan.id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)

    if request.method == "POST":

        title = request.POST.get("title", "").strip()

        description = request.POST.get("description", "").strip()

        field_ids = request.POST.getlist("fields")

        skill_ids = request.POST.getlist("skills")

        if not title:

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": "Recruitment title is required.",
                },
            )

        if not field_ids:

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": "Please select at least one field.",
                },
            )

        if not skill_ids:

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": "Please select at least one required skill.",
                },
            )

        skill_ids = list(dict.fromkeys(skill_ids))

        if len(skill_ids) > 35:

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": "You can select a maximum of 35 skills.",
                },
            )

        fields = SkillType.objects.filter(id__in=field_ids)

        if fields.count() != len(set(field_ids)):

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": "Invalid field selection.",
                },
            )

        skills = Skill.objects.filter(id__in=skill_ids)

        if skills.count() != len(set(skill_ids)):

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": "Invalid skill selection.",
                },
            )

        active_recruitments = ClanRecruitment.objects.filter(
            clan=clan, expires_at__gt=timezone.now()
        ).count()

        if active_recruitments >= 2:

            return render(
                request,
                "clans/create_recruitment.html",
                {
                    "clan": clan,
                    "skill_types": SkillType.objects.all(),
                    "error": (
                        "Your clan already has " "2 active recruitment requests."
                    ),
                },
            )

        recruitment = ClanRecruitment.objects.create(
            clan=clan,
            created_by=profile,
            title=title,
            description=description,
            expires_at=timezone.now() + timedelta(days=7),
        )

        recruitment.fields.set(fields)

        ClanRecruitmentSkill.objects.bulk_create(
            [
                ClanRecruitmentSkill(recruitment=recruitment, skill=skill)
                for skill in skills
            ]
        )

        return redirect("clan_profile", clan_id=clan.id)

    return render(
        request,
        "clans/create_recruitment.html",
        {"clan": clan, "skill_types": SkillType.objects.all()},
    )


@login_required
def clan_story_viewers(request, story_id):

    student = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory.objects.select_related("clan"), id=story_id)

    membership = ClanMember.objects.filter(clan=story.clan, student=student).first()

    if not membership:
        return redirect("clan_profile", clan_id=story.clan_id)

    viewers = (
        ClanStoryView.objects.filter(story=story)
        .select_related("student", "student__user")
        .order_by("-viewed_at")
    )

    likes = (
        ClanStoryLike.objects.filter(story=story)
        .select_related("student", "student__user")
        .order_by("-created_at")
    )

    return render(
        request,
        "clans/story_viewers.html",
        {
            "story": story,
            "viewers": viewers,
            "likes": likes,
        },
    )


@login_required
@block_suspended_student
def send_clan_invitation(request, student_id):

    if request.method != "POST":
        return redirect("view_profile", student_id=student_id)

    sender = get_object_or_404(StudentProfile, user=request.user)

    invited_student = get_object_or_404(StudentProfile, id=student_id)

    sender_membership = (
        ClanMember.objects.filter(student=sender).select_related("clan").first()
    )

    if not sender_membership:
        return redirect("view_profile", student_id=student_id)

    if sender_membership.role not in ["leader", "co_leader"]:
        return redirect("view_profile", student_id=student_id)

    clan = sender_membership.clan

    if sender.id == invited_student.id:
        return redirect("view_profile", student_id=student_id)

    if ClanMember.objects.filter(student=invited_student).exists():

        return redirect("view_profile", student_id=student_id)

    current_member_count = ClanMember.objects.filter(clan=clan).count()

    if current_member_count >= 12:
        return redirect("view_profile", student_id=student_id)

    if ClanInvitation.objects.filter(
        clan=clan, invited_student=invited_student, status="pending"
    ).exists():

        return redirect("view_profile", student_id=student_id)

    ClanInvitation.objects.create(
        clan=clan, invited_student=invited_student, invited_by=sender
    )

    return redirect("view_profile", student_id=student_id)


@login_required
@block_suspended_student
def accept_clan_invitation(request, invitation_id):

    if request.method != "POST":
        return redirect("profile")

    student = get_object_or_404(StudentProfile, user=request.user)

    invitation = get_object_or_404(
        ClanInvitation.objects.select_related("clan", "invited_student"),
        id=invitation_id,
    )

    if invitation.invited_student_id != student.id:
        return redirect("profile")

    if invitation.status != "pending":
        return redirect("profile")

    if ClanMember.objects.filter(student=student).exists():

        return redirect("profile")

    clan = invitation.clan

    if ClanMember.objects.filter(clan=clan).count() >= 12:

        return redirect("profile")

    membership = ClanMember.objects.create(clan=clan, student=student, role="member")
    _record_membership_join(membership)

    invitation.status = "accepted"
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])

    return redirect("profile")


@login_required
@block_suspended_student
def send_clan_join_request(request, clan_id):

    if request.method != "POST":
        return redirect("clan_profile", clan_id=clan_id)

    student = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    existing_membership = ClanMember.objects.filter(student=student).first()

    if existing_membership:

        # If already in this clan,
        # simply open that clan profile.
        if existing_membership.clan_id == clan.id:
            return redirect("clan_profile", clan_id=clan.id)

        # Already belongs to another clan.
        return redirect("clan_profile", clan_id=clan.id)

    member_count = ClanMember.objects.filter(clan=clan).count()

    if member_count >= 12:
        return redirect("clan_profile", clan_id=clan.id)

    existing_request = ClanJoinRequest.objects.filter(
        clan=clan, student=student, status="pending"
    ).first()

    if existing_request:
        return redirect("clan_profile", clan_id=clan.id)

    existing_invitation = ClanInvitation.objects.filter(
        clan=clan, invited_student=student, status="pending"
    ).first()

    if existing_invitation:

        return redirect("clan_profile", clan_id=clan.id)

    ClanJoinRequest.objects.create(clan=clan, student=student)

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def cancel_clan_join_request(request, request_id):

    if request.method != "POST":
        return redirect("global_recruitments")

    student = get_object_or_404(StudentProfile, user=request.user)

    join_request = get_object_or_404(
        ClanJoinRequest.objects.select_related("clan"), id=request_id
    )

    if join_request.student_id != student.id:
        return redirect("global_recruitments")

    if join_request.status != "pending":
        return redirect("global_recruitments")

    join_request.status = "cancelled"
    join_request.responded_at = timezone.now()

    join_request.save(update_fields=["status", "responded_at"])

    return redirect("global_recruitments")


@login_required
@block_suspended_student
def accept_clan_join_request(request, request_id):

    if request.method != "POST":
        return redirect("profile")

    leader = get_object_or_404(StudentProfile, user=request.user)

    join_request = get_object_or_404(
        ClanJoinRequest.objects.select_related("clan", "student"), id=request_id
    )

    if join_request.status != "pending":
        return redirect("profile")

    clan = join_request.clan

    membership = ClanMember.objects.filter(clan=clan, student=leader).first()

    if not membership:
        return redirect("profile")

    if membership.role not in ["leader", "co_leader"]:
        return redirect("profile")

    member_count = ClanMember.objects.filter(clan=clan).count()

    if member_count >= 12:
        return redirect("clan_profile", clan_id=clan.id)

    existing_membership = ClanMember.objects.filter(
        student=join_request.student
    ).first()

    if existing_membership:
        join_request.status = "cancelled"

        join_request.responded_at = timezone.now()

        join_request.save(update_fields=["status", "responded_at"])

        return redirect("clan_profile", clan_id=clan.id)

    membership = ClanMember.objects.create(
        clan=clan, student=join_request.student, role="member"
    )
    _record_membership_join(membership)

    join_request.status = "accepted"

    join_request.responded_at = timezone.now()

    join_request.save(update_fields=["status", "responded_at"])

    ClanJoinRequest.objects.filter(
        student=join_request.student, status="pending"
    ).exclude(id=join_request.id).update(
        status="cancelled", responded_at=timezone.now()
    )

    ClanInvitation.objects.filter(
        invited_student=join_request.student, status="pending"
    ).update(status="cancelled", responded_at=timezone.now())

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def reject_clan_join_request(request, request_id):

    if request.method != "POST":
        return redirect("profile")

    leader = get_object_or_404(StudentProfile, user=request.user)

    join_request = get_object_or_404(
        ClanJoinRequest.objects.select_related("clan"), id=request_id
    )

    if join_request.status != "pending":
        return redirect("profile")

    clan = join_request.clan

    membership = ClanMember.objects.filter(clan=clan, student=leader).first()

    if not membership:
        return redirect("profile")

    if membership.role not in ["leader", "co_leader"]:
        return redirect("profile")

    join_request.status = "rejected"

    join_request.responded_at = timezone.now()

    join_request.save(update_fields=["status", "responded_at"])

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def reject_clan_invitation(request, invitation_id):

    if request.method != "POST":
        return redirect("profile")

    student = get_object_or_404(StudentProfile, user=request.user)

    invitation = get_object_or_404(ClanInvitation, id=invitation_id)

    if invitation.invited_student_id != student.id:
        return redirect("profile")

    if invitation.status != "pending":
        return redirect("profile")

    invitation.status = "rejected"
    invitation.responded_at = timezone.now()

    invitation.save(update_fields=["status", "responded_at"])

    return redirect("profile")


def login_view(request):

    if request.method == "POST":

        username_or_email = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        # -------------------------------------------------
        # CAMPUS ADMIN LOGIN
        # -------------------------------------------------
        if (
            settings.CAMPUS_ADMIN_USERNAME
            and settings.CAMPUS_ADMIN_PASSWORD
            and secrets.compare_digest(
                username_or_email, settings.CAMPUS_ADMIN_USERNAME
            )
            and secrets.compare_digest(password, settings.CAMPUS_ADMIN_PASSWORD)
        ):
            logout(request)
            request.session["is_admin"] = True

            return redirect("campus_admin_dashboard")

        # -------------------------------------------------
        # STUDENT LOGIN USING USERNAME
        # -------------------------------------------------
        user = authenticate(request, username=username_or_email, password=password)

        # -------------------------------------------------
        # STUDENT LOGIN USING EMAIL
        # -------------------------------------------------
        if user is None:

            matching_user = User.objects.filter(email__iexact=username_or_email).first()

            if matching_user:
                user = authenticate(
                    request, username=matching_user.username, password=password
                )

        # -------------------------------------------------
        # LOGIN SUCCESS
        # -------------------------------------------------
        if user is not None:

            request.session.pop("is_admin", None)

            login(request, user)

            return redirect("home")

        # -------------------------------------------------
        # LOGIN FAILED
        # -------------------------------------------------
        return render(
            request, "signup.html", {"error": "Invalid username/email or password."}
        )

    return render(request, "signup.html")


def register_view(request):

    return render(request, "signup.html")


def forgot_password(request):
    return render(request, "forgot_password.html")


def send_password_reset_otp(request):

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    email = request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse(
            {"success": False, "error": "Email address is required."}, status=400
        )

    # ==========================================
    # CHECK 5 OTP SENDS / 24 HOURS
    # ==========================================

    sends_used = _otp_send_limit(email, "password_reset")

    if sends_used >= OTP_MAX_SENDS_24_HOURS:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "You have used all 5 OTP requests "
                    "allowed for this email address. "
                    "No more OTPs can be sent until "
                    "the 24-hour limit resets."
                ),
                "limit_reached": True,
                "sends_remaining": 0,
            },
            status=429,
        )

    # ==========================================
    # FIND USER
    # ==========================================

    user = User.objects.filter(email__iexact=email, is_active=True).first()

    # Don't reveal whether the email is registered.
    if not user:

        return JsonResponse(
            {
                "success": True,
                "message": ("If the email is registered, " "an OTP has been sent."),
                "sends_remaining": (OTP_MAX_SENDS_24_HOURS - sends_used),
            }
        )

    # ==========================================
    # DETERMINE OTP NUMBER
    # ==========================================

    # First OTP = 180 seconds
    # OTP 2-5 = 120 seconds

    otp_number = sends_used + 1

    if otp_number == 1:
        expiry_seconds = 180
    else:
        expiry_seconds = 120

    # ==========================================
    # GENERATE OTP
    # ==========================================

    otp = str(random.randint(100000, 999999))

    request.session["password_reset_otp"] = otp

    request.session["password_reset_otp_created_at"] = timezone.now().timestamp()

    request.session["password_reset_otp_attempts"] = 0

    request.session["password_reset_email"] = email

    request.session["password_reset_user_id"] = user.id

    # IMPORTANT:
    # Store the expiry of THIS particular OTP.
    request.session["password_reset_otp_expiry"] = expiry_seconds

    # Store which OTP this is.
    request.session["password_reset_otp_number"] = otp_number

    # ==========================================
    # SEND EMAIL
    # ==========================================

    try:

        send_mail(
            "Campus Clans - Password Reset OTP",
            f"""
Your Campus Clans password reset OTP is:

{otp}

This OTP expires in {expiry_seconds} seconds.

You have {OTP_MAX_SENDS_24_HOURS - sends_used - 1}
OTP request(s) remaining today.

If you did not request this password reset,
please ignore this email.
""",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )

    except Exception:

        _clear_password_reset_otp(request)

        return JsonResponse(
            {"success": False, "error": ("Unable to send OTP. " "Please try again.")},
            status=500,
        )

    # ==========================================
    # RECORD SUCCESSFUL OTP SEND
    # ==========================================

    OTPRequestLog.objects.create(email=email, purpose="password_reset")

    sends_used += 1

    sends_remaining = OTP_MAX_SENDS_24_HOURS - sends_used

    # ==========================================
    # RESPONSE
    # ==========================================

    return JsonResponse(
        {
            "success": True,
            "message": ("If the email is registered, " "an OTP has been sent."),
            "expires_in": expiry_seconds,
            "sends_remaining": sends_remaining,
            "otp_number": otp_number,
            "limit_reached": (sends_remaining == 0),
        }
    )


def verify_password_reset_otp(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    otp = request.POST.get("otp", "").strip()
    saved_otp = request.session.get("password_reset_otp")
    created_at = request.session.get("password_reset_otp_created_at")
    attempts = int(request.session.get("password_reset_otp_attempts", 0))

    if (
        not saved_otp
        or not request.session.get("password_reset_user_id")
        or _otp_is_expired(created_at, OTP_RESEND_EXPIRY_SECONDS)
    ):
        _clear_password_reset_otp(request)
        return JsonResponse(
            {"success": False, "error": "OTP has expired or was not requested."},
            status=400,
        )

    if attempts >= OTP_MAX_ATTEMPTS:
        _clear_password_reset_otp(request)
        return JsonResponse(
            {
                "success": False,
                "error": "Too many incorrect attempts. Please request a new OTP.",
            },
            status=429,
        )

    if otp != saved_otp:
        attempts += 1
        request.session["password_reset_otp_attempts"] = attempts
        remaining = OTP_MAX_ATTEMPTS - attempts
        if remaining <= 0:
            _clear_password_reset_otp(request)
            return JsonResponse(
                {
                    "success": False,
                    "error": "Too many incorrect attempts. Please request a new OTP.",
                },
                status=429,
            )
        return JsonResponse(
            {
                "success": False,
                "error": f"Invalid OTP. {remaining} attempts remaining.",
            },
            status=400,
        )

    request.session["password_reset_verified"] = True
    request.session.pop("password_reset_otp", None)
    request.session.pop("password_reset_otp_created_at", None)
    request.session.pop("password_reset_otp_attempts", None)

    return JsonResponse({"success": True, "message": "OTP verified successfully."})


def reset_password(request):
    if request.method != "POST":
        return redirect("forgot_password")

    if not request.session.get("password_reset_verified"):
        return render(
            request, "forgot_password.html", {"error": "Please verify the OTP first."}
        )

    user_id = request.session.get("password_reset_user_id")
    email = request.session.get("password_reset_email")
    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")

    user = get_object_or_404(User, id=user_id, email__iexact=email, is_active=True)

    if password != confirm_password:
        return render(
            request, "forgot_password.html", {"error": "Passwords do not match."}
        )

    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return render(
            request,
            "forgot_password.html",
            {"error": " ".join(exc.messages)},
        )

    user.set_password(password)
    user.save(update_fields=["password"])
    _clear_password_reset_otp(request)
    request.session.pop("password_reset_verified", None)

    return redirect("login")


@login_required
def search(request):

    query = request.GET.get("q", "").strip()

    students = []
    clans = []

    if query:

        if query.startswith("@"):

            student_query = query[1:].strip()

            if student_query:

                students = (
                    StudentProfile.objects.filter(
                        Q(user__username__icontains=student_query)
                        | Q(name__icontains=student_query)
                        | Q(department__icontains=student_query)
                        | Q(branch__icontains=student_query)
                        | Q(student_skills__skill__name__icontains=student_query)
                    )
                    .select_related("user")
                    .distinct()[:10]
                )

        else:

            clans = Clan.objects.filter(
                Q(name__icontains=query)
                | Q(speciality__icontains=query)
                | Q(profile_description__icontains=query)
                | Q(description__icontains=query)
            ).distinct()[:10]

    return render(
        request,
        "user/search_results.html",
        {
            "query": query,
            "students": students,
            "clans": clans,
        },
    )


@login_required
def student_search(request):

    query = request.GET.get("q", "").strip()

    students = []

    if query:

        current_student = get_object_or_404(StudentProfile, user=request.user)

        results = (
            StudentProfile.objects.filter(
                Q(name__icontains=query) | Q(user__username__icontains=query)
            )
            .exclude(id=current_student.id)
            .select_related("user", "clan_membership__clan")
            .order_by("name")[:10]
        )

        for student in results:

            membership = getattr(student, "clan_membership", None)

            students.append(
                {
                    "id": student.id,
                    "name": student.name,
                    "username": student.user.username,
                    "department": student.department,
                    "profile_picture": (
                        student.profile_picture.url if student.profile_picture else None
                    ),
                    "in_clan": membership is not None,
                    "clan_name": (membership.clan.name if membership else None),
                }
            )

    return JsonResponse({"students": students})

@login_required
def events(request):

    profile = StudentProfile.objects.filter(
        user=request.user
    ).first()

    if not profile:
        logout(request)
        return redirect("login")

    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    my_clan = membership.clan if membership else None

    now = timezone.now()

    event_list = (
        Event.objects
        .filter(end_date__gte=now)
        .prefetch_related("media")
        .order_by("end_date")
    )

    for event in event_list:
        selection_deadline = event.end_date - timedelta(hours=24)
        event.clan_selection_editable = now < selection_deadline

    participations = (
        EventParticipation.objects
        .filter(
            event_id__in=event_list.values("id")
        )
        .select_related(
            "clan",
            "student",
            "student__user",
        )
        .prefetch_related(
            "selected_members__student",
            "selected_members__student__user",
        )
    )

    student_participated_event_ids = set(
        participations
        .filter(
            participant_type="student",
            student=profile,
        )
        .values_list(
            "event_id",
            flat=True
        )
    )

    clan_participated_event_ids = set()

    if my_clan:

        clan_participated_event_ids = set(
            participations
            .filter(
                participant_type="clan",
                clan=my_clan,
            )
            .values_list(
                "event_id",
                flat=True
            )
        )

    is_clan_leader = bool(
        membership
        and membership.role in [
            "leader",
            "co_leader",
        ]
    )

    is_my_clan_suspended = False

    if my_clan:

        is_my_clan_suspended = (
            ClanSuspension.objects.filter(
                clan=my_clan,
                is_active=True,
                end_date__gt=now,
            )
            .exists()
        )

    return render(
        request,
        "user/events.html",
        {
            "events": event_list,
            "profile": profile,
            "membership": membership,
            "my_clan": my_clan,

            "student_participated_event_ids":
                student_participated_event_ids,

            "clan_participated_event_ids":
                clan_participated_event_ids,

            "is_clan_leader":
                is_clan_leader,

            "is_my_clan_suspended":
                is_my_clan_suspended,
        },
    )

@login_required
def search_suggestions(request):

    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"students": [], "clans": [], "events": []})

    students = []
    clans = []

    if query.startswith("@"):

        student_query = query[1:].strip()

        if student_query:

            student_results = (
                StudentProfile.objects.filter(
                    Q(user__username__icontains=student_query)
                    | Q(name__icontains=student_query)
                    | Q(department__icontains=student_query)
                    | Q(branch__icontains=student_query)
                    | Q(student_skills__skill__name__icontains=student_query)
                )
                .select_related("user")
                .distinct()[:5]
            )

            students = [
                {
                    "id": student.id,
                    "username": student.user.username,
                    "name": student.name,
                    "department": student.department,
                    "branch": student.branch,
                }
                for student in student_results
            ]

    else:

        clan_results = Clan.objects.filter(
            Q(name__icontains=query)
            | Q(speciality__icontains=query)
            | Q(profile_description__icontains=query)
            | Q(description__icontains=query)
        ).distinct()[:5]

        clans = [
            {
                "id": clan.id,
                "name": clan.name,
                "speciality": clan.speciality,
            }
            for clan in clan_results
        ]

    return JsonResponse({"students": students, "clans": clans, "events": []})


def check_clan_name(request):
    name = request.GET.get("name", "").strip()

    if not name:
        return JsonResponse(
            {"available": False, "message": "Clan name cannot be empty."}
        )

    exists = Clan.objects.filter(name__iexact=name).exists()

    if exists:
        return JsonResponse(
            {"available": False, "message": "Clan name is already taken."}
        )

    return JsonResponse({"available": True, "message": "Clan name is available."})


@login_required
@block_suspended_student
def create_clan(request):

    profile = get_object_or_404(StudentProfile, user=request.user)

    # User is already in a clan
    if ClanMember.objects.filter(student=profile).exists():
        return redirect("home")

    if request.method == "POST":

        name = request.POST.get("name", "").strip()

        speciality = request.POST.get("speciality", "").strip()

        profile_description = request.POST.get("profile_description", "").strip()

        description = request.POST.get("description", "").strip()

        selected_student_id = request.POST.get("member", "").strip()

        # -----------------------------
        # CLAN NAME
        # -----------------------------

        if not name:
            return render(
                request, "clans/create_clans.html", {"error": "Clan name is required."}
            )

        # Final server-side duplicate check.
        # JavaScript availability checking is only
        # for user convenience.
        if Clan.objects.filter(name__iexact=name).exists():
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("A clan with this name " "already exists.")},
            )

        # -----------------------------
        # SPECIALITY
        # -----------------------------

        if not speciality:
            return render(
                request, "clans/create_clans.html", {"error": "Speciality is required."}
            )

        # -----------------------------
        # PROFILE DESCRIPTION
        # -----------------------------

        if len(profile_description) > 50:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("Profile description must be " "50 characters or less.")},
            )

        # -----------------------------
        # CLAN DESCRIPTION
        # -----------------------------

        word_count = len(description.split())

        if word_count > 250:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("Clan description must be " "250 words or less.")},
            )

        # -----------------------------
        # SECOND MEMBER
        # -----------------------------

        if not selected_student_id:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("Please search and select " "one student for your clan.")},
            )

        selected_student = get_object_or_404(StudentProfile, id=selected_student_id)

        # Cannot select yourself
        if selected_student.id == profile.id:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("You cannot select yourself " "as the second member.")},
            )

        # Student already belongs to another clan.
        # This remains a server-side security check
        # even if the frontend disables that student.
        if ClanMember.objects.filter(student=selected_student).exists():
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("This student is already " "a member of another clan.")},
            )

        # -----------------------------
        # CREATE CLAN
        # -----------------------------

        clan = Clan.objects.create(
            name=name,
            speciality=speciality,
            profile_description=profile_description,
            description=description,
            created_by=profile,
            logo=request.FILES.get("logo"),
            banner=request.FILES.get("banner"),
        )

        # -----------------------------
        # LEADER
        # -----------------------------

        leader_membership = ClanMember.objects.create(
            clan=clan, student=profile, role="leader"
        )

        _record_membership_join(leader_membership)

        # -----------------------------
        # CO-LEADER
        # -----------------------------

        co_leader_membership = ClanMember.objects.create(
            clan=clan, student=selected_student, role="co_leader"
        )

        _record_membership_join(co_leader_membership)

        return redirect("clan_profile", clan_id=clan.id)

    return render(request, "clans/create_clans.html")


@login_required
@block_suspended_student
def edit_clan(request, clan_id):

    profile = StudentProfile.objects.get(user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    members = (
        ClanMember.objects.filter(clan=clan)
        .select_related("student", "student__user")
        .order_by("-role", "student__name")
    )

    if request.method == "POST":

        name = request.POST.get("name", "").strip()

        speciality = request.POST.get("speciality", "").strip()

        profile_description = request.POST.get("profile_description", "").strip()

        description = request.POST.get("description", "").strip()

        if not name:
            return render(
                request,
                "clans/edit_clan.html",
                {"clan": clan, "members": members, "error": "Clan name is required."},
            )

        if len(profile_description) > 50:
            return render(
                request,
                "clans/edit_clan.html",
                {
                    "clan": clan,
                    "members": members,
                    "error": "Profile description must be 50 characters or less.",
                },
            )

        if len(description.split()) > 250:
            return render(
                request,
                "clans/edit_clan.html",
                {
                    "clan": clan,
                    "members": members,
                    "error": "Clan description must be 250 words or less.",
                },
            )

        if Clan.objects.filter(name__iexact=name).exclude(id=clan.id).exists():

            return render(
                request,
                "clans/edit_clan.html",
                {
                    "clan": clan,
                    "members": members,
                    "error": "A clan with this name already exists.",
                },
            )

        clan.name = name
        clan.speciality = speciality
        clan.profile_description = profile_description
        clan.description = description

        if request.FILES.get("logo"):

            old_logo = clan.logo

            clan.logo = request.FILES.get("logo")

            delete_media_file(old_logo)

        if request.FILES.get("banner"):

            old_banner = clan.banner

            clan.banner = request.FILES.get("banner")

            delete_media_file(old_banner)

        clan.save()

        return redirect("clan_profile", clan_id=clan.id)

    return render(
        request,
        "clans/edit_clan.html",
        {
            "clan": clan,
            "members": members,
        },
    )

@login_required
@block_suspended_student
def save_event_clan_members(request, event_id):

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "message": "POST request required.",
            },
            status=405,
        )

    event = get_object_or_404(Event, id=event_id)

    now = timezone.now()

    # ---------------------------------
    # EVENT ENDED
    # ---------------------------------

    if now >= event.end_date:
        return JsonResponse(
            {
                "success": False,
                "message": "The event has already ended.",
            },
            status=400,
        )

    # ---------------------------------
    # EVENT MUST ALLOW CLANS
    # ---------------------------------

    if event.participant_type not in ["clan", "both"]:
        return JsonResponse(
            {
                "success": False,
                "message": "This event does not allow clan participation.",
            },
            status=400,
        )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    # ---------------------------------
    # CHECK CLAN MEMBERSHIP
    # ---------------------------------

    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    if not membership:
        return JsonResponse(
            {
                "success": False,
                "message": "You are not a member of any clan.",
            },
            status=400,
        )

    if membership.role not in ["leader", "co_leader"]:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Only the clan leader or co-leader "
                    "can select representatives."
                ),
            },
            status=403,
        )

    clan = membership.clan

    if clan_is_suspended(clan):
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Your clan is suspended and cannot "
                    "participate in events."
                ),
            },
            status=403,
        )

    # ---------------------------------
    # 24-HOUR CUTOFF
    # ---------------------------------

    selection_cutoff = event.end_date - timedelta(hours=24)

    editing_locked = now >= selection_cutoff

    # ---------------------------------
    # GET JSON DATA
    # ---------------------------------

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request data.",
            },
            status=400,
        )

    member_ids = data.get("member_ids")

    if not isinstance(member_ids, list):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid representative list.",
            },
            status=400,
        )

    # Convert IDs safely to integers
    try:
        member_ids = list(
            dict.fromkeys(
                int(member_id)
                for member_id in member_ids
            )
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid member ID.",
            },
            status=400,
        )

    # ---------------------------------
    # REPRESENTATIVES ARE REQUIRED
    # ---------------------------------

    if not member_ids:
        return JsonResponse(
            {
                "success": False,
                "message": "Select at least one representative.",
            },
            status=400,
        )

    # ---------------------------------
    # VERIFY ALL SELECTED MEMBERS
    # ARE CURRENT CLAN MEMBERS
    # ---------------------------------

    current_members = (
        ClanMember.objects
        .filter(
            clan=clan,
            student_id__in=member_ids,
        )
        .values_list(
            "student_id",
            flat=True,
        )
    )

    current_member_ids = set(current_members)

    invalid_ids = [
        member_id
        for member_id in member_ids
        if member_id not in current_member_ids
    ]

    if invalid_ids:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "One or more selected students "
                    "are no longer members of this clan."
                ),
            },
            status=400,
        )

    # =================================
    # GET / CREATE PARTICIPATION
    # =================================

    participation = (
        EventParticipation.objects
        .filter(
            event=event,
            participant_type="clan",
            clan=clan,
        )
        .first()
    )

    # ---------------------------------
    # NEW PARTICIPATION
    #
    # This is the important late-join
    # case.
    # ---------------------------------

    if participation is None:

        participation = EventParticipation.objects.create(
            event=event,
            participant_type="clan",
            clan=clan,
            student=profile,
        )

        # If we are inside the final 24 hours,
        # this newly-created representative list
        # is immediately locked.
        created_now = True

    else:
        created_now = False

    # ---------------------------------
    # EXISTING PARTICIPATION:
    # CHECK 24-HOUR LOCK
    # ---------------------------------

    if not created_now and editing_locked:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Representative selection is locked "
                    "because the event ends within 24 hours."
                ),
                "editing_locked": True,
            },
            status=403,
        )

    # ---------------------------------
    # SAVE REPRESENTATIVES
    # ---------------------------------

    with transaction.atomic():

        EventClanParticipant.objects.filter(
            participation=participation
        ).delete()

        EventClanParticipant.objects.bulk_create(
            [
                EventClanParticipant(
                    participation=participation,
                    student_id=member_id,
                )
                for member_id in member_ids
            ]
        )

    # ---------------------------------
    # RESPONSE
    # ---------------------------------

    return JsonResponse(
        {
            "success": True,
            "message": (
                "Representatives confirmed successfully."
            ),
            "participation_id": participation.id,
            "editing_locked": (
                now >= selection_cutoff
            ),
            "representative_count": len(member_ids),
        }
    )

@login_required
@block_suspended_student
def reject_clan_leave_request(request, request_id):

    if request.method != "POST":
        return redirect("profile")

    approver = get_object_or_404(StudentProfile, user=request.user)

    leave_request = get_object_or_404(
        ClanLeaveRequest.objects.select_related("clan"), id=request_id
    )

    if leave_request.status != "pending":
        return redirect("profile")

    clan = leave_request.clan

    approver_membership = ClanMember.objects.filter(clan=clan, student=approver).first()

    if not approver_membership:
        return redirect("profile")

    if approver_membership.role not in ["leader", "co_leader"]:
        return redirect("profile")

    leave_request.status = "rejected"
    leave_request.responded_at = timezone.now()

    leave_request.save(update_fields=["status", "responded_at"])

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def accept_clan_leave_request(request, request_id):

    if request.method != "POST":
        return redirect("profile")

    approver = get_object_or_404(StudentProfile, user=request.user)

    leave_request = get_object_or_404(
        ClanLeaveRequest.objects.select_related("clan", "student"), id=request_id
    )

    if leave_request.status != "pending":
        return redirect("profile")

    clan = leave_request.clan

    approver_membership = ClanMember.objects.filter(clan=clan, student=approver).first()

    if not approver_membership:
        return redirect("profile")

    # Leader or Co-Leader only
    if approver_membership.role not in ["leader", "co_leader"]:
        return redirect("profile")

    if leave_request.student_id == approver.id:
        return redirect("clan_profile", clan_id=clan.id)

    member = ClanMember.objects.filter(clan=clan, student=leave_request.student).first()

    if not member:
        leave_request.status = "cancelled"
        leave_request.responded_at = timezone.now()
        leave_request.save(update_fields=["status", "responded_at"])

        return redirect("clan_profile", clan_id=clan.id)

    if member.role == "leader":
        return redirect("clan_profile", clan_id=clan.id)

    _record_membership_leave(member)
    member.delete()

    leave_request.status = "accepted"
    leave_request.responded_at = timezone.now()

    leave_request.save(update_fields=["status", "responded_at"])

    if ClanMember.objects.filter(clan=clan).count() < 2:

        _close_clan_membership_histories(clan)
        delete_clan_media(clan)

        clan.delete()

        return redirect("home")

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def request_clan_leave(request, clan_id):

    if request.method != "POST":
        return redirect("clan_profile", clan_id=clan_id)

    student = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=student).first()

    if not membership:
        return redirect("clan_profile", clan_id=clan.id)

    if membership.role == "leader":
        return redirect("clan_profile", clan_id=clan.id)

    existing_request = ClanLeaveRequest.objects.filter(
        clan=clan, student=student, status="pending"
    ).exists()

    if existing_request:
        return redirect("clan_profile", clan_id=clan.id)

    ClanLeaveRequest.objects.create(clan=clan, student=student)

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def remove_clan_member(request, clan_id, member_id):

    if request.method != "POST":
        return redirect("edit_clan", clan_id=clan_id)

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    member = get_object_or_404(ClanMember, id=member_id, clan=clan)

    if member.student_id == clan.created_by_id:
        return redirect("edit_clan", clan_id=clan.id)

    if member.role == "co_leader":
        return redirect("edit_clan", clan_id=clan.id)

    _record_membership_leave(member)
    member.delete()

    if ClanMember.objects.filter(clan=clan).count() < 2:
        _close_clan_membership_histories(clan)
        delete_clan_media(clan)

        clan.delete()
        return redirect("home")

    return redirect("edit_clan", clan_id=clan.id)


def delete_clan_media(clan):
    """
    Delete all physical media belonging to a clan.
    """

    # Clan logo
    delete_media_file(clan.logo)

    # Clan banner
    delete_media_file(clan.banner)

    # Post images
    for post in clan.posts.all():
        delete_media_file(post.image)

    # Story images
    for story in clan.stories.all():
        delete_media_file(story.image)


@login_required
@block_suspended_student
def delete_clan(request, clan_id):

    profile = StudentProfile.objects.get(user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    if request.method == "POST":

        _close_clan_membership_histories(clan)

        delete_clan_media(clan)

        clan.delete()

        return redirect("home")

    return redirect("edit_clan", clan_id=clan.id)


@login_required
@block_suspended_student
def change_clan_member_role(request, clan_id, member_id):

    if request.method != "POST":
        return redirect("edit_clan", clan_id=clan_id)

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    member = get_object_or_404(ClanMember, id=member_id, clan=clan)

    if member.student_id == clan.created_by_id:
        return redirect("edit_clan", clan_id=clan.id)

    role = request.POST.get("role")

    if role not in ["member", "co_leader"]:
        return redirect("edit_clan", clan_id=clan.id)

    if role == "co_leader":

        existing_co_leader = (
            ClanMember.objects.filter(clan=clan, role="co_leader")
            .exclude(id=member.id)
            .exists()
        )

        if existing_co_leader:
            return redirect("edit_clan", clan_id=clan.id)

    member.role = role
    member.save(update_fields=["role"])

    return redirect("edit_clan", clan_id=clan.id)


@login_required
def clan_profile(request, clan_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    # =========================================================
    # CLAN
    # =========================================================

    clan_cache_key = f"clan:{clan_id}"
    clan = cache.get(clan_cache_key)

    if clan is None:
        clan = get_object_or_404(Clan, id=clan_id)
        cache.set(clan_cache_key, clan, 300)

    # =========================================================
    # MEMBERS
    # =========================================================

    members_cache_key = f"clan:{clan_id}:members"
    members = cache.get(members_cache_key)

    if members is None:
        members = list(
            ClanMember.objects
            .filter(clan=clan)
            .select_related("student", "student__user")
            .order_by("-role", "joined_at")
        )

        cache.set(
            members_cache_key,
            members,
            300
        )

    # =========================================================
    # CURRENT USER MEMBERSHIP
    # =========================================================

    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    is_member = (
        membership is not None
        and membership.clan_id == clan.id
    )

    is_creator = clan.created_by_id == profile.id

    # =========================================================
    # JOIN / INVITATION STATUS
    # =========================================================

    pending_join_request = ClanJoinRequest.objects.filter(
        clan=clan,
        student=profile,
        status="pending"
    ).first()

    pending_invitation = ClanInvitation.objects.filter(
        clan=clan,
        invited_student=profile,
        status="pending"
    ).first()

    # =========================================================
    # CLAN MANAGEMENT PERMISSIONS
    # =========================================================

    can_manage_join_requests = (
        is_member
        and membership.role in ["leader", "co_leader"]
    )

    can_manage_clan_content = can_manage_join_requests

    # =========================================================
    # JOIN REQUESTS
    # =========================================================

    join_requests = []

    if can_manage_join_requests:

        join_requests = (
            ClanJoinRequest.objects
            .filter(
                clan=clan,
                status="pending"
            )
            .select_related(
                "student",
                "student__user"
            )
            .order_by("-created_at")
        )

    # =========================================================
    # CLAN SIZE
    # =========================================================

    member_count = len(members)

    clan_full = member_count >= 12

    can_join = (
        not is_member
        and membership is None
        and not pending_join_request
        and not pending_invitation
        and not clan_full
    )

    # =========================================================
    # LEAVE REQUEST
    # =========================================================

    pending_leave_request = ClanLeaveRequest.objects.filter(
        clan=clan,
        student=profile,
        status="pending"
    ).first()

    can_request_leave = (
        is_member
        and membership.role != "leader"
        and not pending_leave_request
    )

    # =========================================================
    # LEAVE REQUESTS
    # =========================================================

    leave_requests = []

    if can_manage_join_requests:

        leave_requests = (
            ClanLeaveRequest.objects
            .filter(
                clan=clan,
                status="pending"
            )
            .select_related(
                "student",
                "student__user"
            )
            .order_by("-created_at")
        )

    # =========================================================
    # CURRENT TIME
    # =========================================================

    now = timezone.now()

    # =========================================================
    # STORIES
    # =========================================================

    stories = (
        ClanStory.objects
        .filter(
            clan=clan,
            expires_at__gt=now
        )
        .annotate(
            viewer_count=Count(
                "views",
                distinct=True
            ),
            like_count=Count(
                "likes",
                distinct=True
            ),
        )
        .order_by("-created_at")
    )

    viewed_story_ids = set(
        ClanStoryView.objects
        .filter(
            story__in=stories,
            student=profile
        )
        .values_list(
            "story_id",
            flat=True
        )
    )

    liked_story_ids = set(
        ClanStoryLike.objects
        .filter(
            story__in=stories,
            student=profile
        )
        .values_list(
            "story_id",
            flat=True
        )
    )

    # =========================================================
    # POSTS
    # =========================================================

    posts = (
        ClanPost.objects
        .filter(clan=clan)
        .select_related(
            "author",
            "author__user"
        )
        .annotate(
            like_count=Count("likes")
        )
        .order_by("-created_at")
    )

    liked_post_ids = set(
        ClanPostLike.objects
        .filter(
            post__in=posts,
            student=profile
        )
        .values_list(
            "post_id",
            flat=True
        )
    )

    # =========================================================
    # RECRUITMENTS
    # =========================================================

    active_recruitments = (
        ClanRecruitment.objects
        .filter(
            clan=clan,
            expires_at__gt=now
        )
        .prefetch_related(
            "fields",
            "recruitment_skills__skill"
        )
        .order_by("-created_at")
    )

    # =========================================================
    # PROJECTS
    # =========================================================

    projects_cache_key = f"clan:{clan_id}:projects"
    clan_projects = cache.get(projects_cache_key)

    if clan_projects is None:

        clan_projects = list(
            ClanProject.objects
            .filter(clan=clan)
            .order_by("-created_at")
        )

        cache.set(
            projects_cache_key,
            clan_projects,
            300
        )

    # =========================================================
    # MESSAGES
    # =========================================================

    clan_messages = (
        ClanMessage.objects
        .filter(clan=clan)
        .order_by("-created_at")
    )

    # =========================================================
    # TROPHIES
    # =========================================================

    clan_trophies = (
        EventTrophy.objects
        .filter(clan=clan)
        .select_related("event")
        .order_by("-awarded_at")
    )

    for trophy in clan_trophies:

        participation = (
            EventParticipation.objects
            .filter(
                event=trophy.event,
                participant_type="clan",
                clan=clan,
            )
            .prefetch_related(
                "selected_members__student",
            )
            .first()
        )

        if participation:
            trophy.representatives = [
                selected.student
                for selected in participation.selected_members.all()
            ]
        else:
            trophy.representatives = []

    # =========================================================
    # UPCOMING EVENTS
    # =========================================================

    upcoming_events = []

    if is_member:

        upcoming_event_participations = (
            EventParticipation.objects
            .filter(
                event__end_date__gte=now,
                clan=clan,
                participant_type="clan",
            )
            .select_related("event")
            .order_by("event__end_date")
        )

        for participation in upcoming_event_participations:

            event = participation.event

            upcoming_events.append(event)

    # =========================================================
    # RENDER
    # =========================================================

    return render(
        request,
        "clans/clan_profile.html",
        {
            "clan": clan,

            "members": members,
            "member_count": member_count,
            "clan_full": clan_full,

            "is_member": is_member,
            "is_creator": is_creator,
            "membership": membership,

            "pending_join_request": pending_join_request,
            "pending_invitation": pending_invitation,

            "can_join": can_join,

            "can_manage_join_requests": can_manage_join_requests,
            "can_manage_clan_content": can_manage_clan_content,

            "join_requests": join_requests,

            "pending_leave_request": pending_leave_request,
            "can_request_leave": can_request_leave,
            "leave_requests": leave_requests,

            "stories": stories,
            "viewed_story_ids": viewed_story_ids,
            "liked_story_ids": liked_story_ids,

            "posts": posts,
            "liked_post_ids": liked_post_ids,

            "active_recruitments": active_recruitments,

            "clan_projects": clan_projects,

            "clan_messages": clan_messages,

            # TROPHIES
            "clan_trophies": clan_trophies,

            # EVENTS
            "upcoming_events": upcoming_events,
        },
    )


@login_required
@block_suspended_student
def like_clan_story(request, story_id):

    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory, id=story_id, expires_at__gt=timezone.now())

    like = ClanStoryLike.objects.filter(story=story, student=profile).first()

    if like:
        like.delete()
        liked = False
    else:
        ClanStoryLike.objects.create(story=story, student=profile)
        liked = True

    like_count = ClanStoryLike.objects.filter(story=story).count()

    return JsonResponse(
        {
            "success": True,
            "liked": liked,
            "like_count": like_count,
        }
    )


@login_required
@block_suspended_student
def create_clan_story(request, clan_id):

    if request.method != "POST":
        return redirect("clan_profile", clan_id=clan_id)

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    if not membership or membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)

    story_type = request.POST.get("story_type", "").strip()

    text = request.POST.get("text", "").strip()

    caption = request.POST.get("caption", "").strip()

    image = request.FILES.get("image")
    video = request.FILES.get("video")

    if story_type not in ["text", "image", "video"]:
        return render(
            request,
            "clans/create_story.html",
            {"clan": clan, "error": "Invalid story type."},
        )

    # TEXT
    if story_type == "text":

        if not text:
            return render(
                request,
                "clans/create_story.html",
                {"clan": clan, "error": "Text story cannot be empty."},
            )

        image = None
        video = None
        caption = ""

    # IMAGE
    elif story_type == "image":

        if not image:
            return render(
                request,
                "clans/create_story.html",
                {"clan": clan, "error": "Please select an image."},
            )

        text = ""
        video = None

    # VIDEO
    elif story_type == "video":

        if not video:
            return render(
                request,
                "clans/create_story.html",
                {"clan": clan, "error": "Please select a video."},
            )

        text = ""
        image = None

        import tempfile
        import os

        temp_path = None

        try:

            suffix = os.path.splitext(video.name)[1]

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:

                temp_path = temp_file.name

                for chunk in video.chunks():
                    temp_file.write(chunk)

            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    temp_path,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode != 0:
                return render(
                    request,
                    "clans/create_story.html",
                    {"clan": clan, "error": "Unable to read the video."},
                )

            try:
                duration = float(result.stdout.strip())
            except (ValueError, TypeError):
                return render(
                    request,
                    "clans/create_story.html",
                    {"clan": clan, "error": "Unable to determine video duration."},
                )

            if duration > 30:
                return render(
                    request,
                    "clans/create_story.html",
                    {
                        "clan": clan,
                        "error": ("Video must be 30 seconds " "or shorter."),
                    },
                )

        except subprocess.TimeoutExpired:

            return render(
                request,
                "clans/create_story.html",
                {"clan": clan, "error": "Video processing took too long."},
            )

        except FileNotFoundError:

            return render(
                request,
                "clans/create_story.html",
                {
                    "clan": clan,
                    "error": ("Video processing is not configured " "on the server."),
                },
            )

        finally:

            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    ClanStory.objects.create(
        clan=clan,
        story_type=story_type,
        text=text,
        caption=caption,
        image=image,
        video=video,
        expires_at=timezone.now() + timedelta(hours=24),
    )

    return redirect("clan_profile", clan_id=clan.id)


@login_required
def view_clan_story(request, story_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(
        ClanStory.objects.select_related("clan"),
        id=story_id,
        expires_at__gt=timezone.now(),
    )

    clan = story.clan

    # Get all active stories from this clan
    stories = list(
        ClanStory.objects.filter(clan=clan, expires_at__gt=timezone.now()).order_by(
            "created_at"
        )
    )

    # Find the position of the story that was clicked
    current_index = next(
        (index for index, item in enumerate(stories) if item.id == story.id), 0
    )

    # Record the current story as viewed
    ClanStoryView.objects.get_or_create(story=story, student=profile)

    # Current story like status
    liked = ClanStoryLike.objects.filter(story=story, student=profile).exists()

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    can_manage = membership is not None and membership.role in ["leader", "co_leader"]

    # Counts for the current story
    viewer_count = ClanStoryView.objects.filter(story=story).count()

    like_count = ClanStoryLike.objects.filter(story=story).count()

    return render(
        request,
        "clans/view_story.html",
        {
            "story": story,
            "stories": stories,
            "current_index": current_index,
            "liked": liked,
            "can_manage": can_manage,
            "viewer_count": viewer_count,
            "like_count": like_count,
        },
    )


@login_required
@block_suspended_student
def record_clan_story_view(request, story_id):

    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory, id=story_id, expires_at__gt=timezone.now())

    ClanStoryView.objects.get_or_create(story=story, student=profile)

    viewer_count = ClanStoryView.objects.filter(story=story).count()

    like_count = ClanStoryLike.objects.filter(story=story).count()

    return JsonResponse(
        {
            "success": True,
            "viewer_count": viewer_count,
            "like_count": like_count,
        }
    )


@login_required
@block_suspended_student
def create_clan_post(request, clan_id):

    if request.method != "POST":
        return redirect("clan_profile", clan_id=clan_id)

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=clan.id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)

    content = request.POST.get("content", "").strip()

    images = request.FILES.getlist("images")

    video = request.FILES.get("video")

    # ---------------------------------
    # POST MUST CONTAIN SOMETHING
    # ---------------------------------

    if not content and not images and not video:

        return redirect("clan_profile", clan_id=clan.id)

    # ---------------------------------
    # CREATE POST
    # ---------------------------------

    post = ClanPost.objects.create(clan=clan, author=profile, content=content)

    # ---------------------------------
    # SAVE MULTIPLE IMAGES
    # ---------------------------------

    for image in images:

        ClanPostImage.objects.create(post=post, image=image)

    # ---------------------------------
    # SAVE VIDEO
    # ---------------------------------

    if video:

        post.video = video

        post.save(update_fields=["video"])

    return redirect("clan_profile", clan_id=clan.id)


@login_required
@block_suspended_student
def toggle_clan_post_like(request, post_id):

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=405)

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost, id=post_id)

    like = ClanPostLike.objects.filter(post=post, student=profile).first()

    # Unlike
    if like:

        like.delete()

        liked = False

    # Like
    else:

        ClanPostLike.objects.create(post=post, student=profile)

        liked = True

    # Get updated count
    like_count = ClanPostLike.objects.filter(post=post).count()

    return JsonResponse({"success": True, "liked": liked, "like_count": like_count})


@login_required
def clan_post_likes(request, post_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=profile).first()

    # Only clan members can see who liked the post
    if not membership:

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":

            return JsonResponse(
                {
                    "success": False,
                    "error": "Only clan members can see who liked this post.",
                },
                status=403,
            )

        return redirect("clan_posts", clan_id=post.clan_id)

    likes = (
        ClanPostLike.objects.filter(post=post)
        .select_related("student", "student__user")
        .order_by("-created_at")
    )

    # AJAX request → return JSON
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":

        liked_by = []

        for like in likes:

            student = like.student

            liked_by.append(
                {
                    "id": student.id,
                    "name": student.name,
                    "username": student.user.username,
                    "profile_picture": (
                        student.profile_picture.url if student.profile_picture else None
                    ),
                }
            )

        return JsonResponse(
            {"success": True, "likes": liked_by, "count": len(liked_by)}
        )

    # Normal request → keep existing page support
    return render(request, "clans/post_likes.html", {"post": post, "likes": likes})


def send_otp(request):

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    email = request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse(
            {"success": False, "error": "Email address is required."}, status=400
        )

    # ==========================================
    # CHECK WHETHER EMAIL IS ALREADY REGISTERED
    # ==========================================

    if User.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {"success": False, "error": "This email is already registered."}, status=400
        )

    if StudentProfile.objects.filter(email__iexact=email).exists():
        return JsonResponse(
            {"success": False, "error": "This email is already registered."}, status=400
        )

    # ==========================================
    # CHECK 5 OTP SENDS / ROLLING 24 HOURS
    # ==========================================

    sends_used = _otp_send_limit(email, "registration")

    if sends_used >= OTP_MAX_SENDS_24_HOURS:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "You have used all 5 OTP requests "
                    "allowed for this email address. "
                    "No more OTPs can be sent until "
                    "the 24-hour limit resets."
                ),
                "limit_reached": True,
                "sends_remaining": 0,
            },
            status=429,
        )

    # ==========================================
    # DETERMINE OTP NUMBER
    # ==========================================

    otp_number = sends_used + 1

    if otp_number == 1:
        expiry_seconds = OTP_FIRST_EXPIRY_SECONDS
    else:
        expiry_seconds = OTP_RESEND_EXPIRY_SECONDS

    # ==========================================
    # GENERATE OTP
    # ==========================================

    otp = str(random.randint(100000, 999999))

    # ==========================================
    # SAVE REGISTRATION DATA IN SESSION
    # ==========================================

    request.session["registration_otp"] = otp

    request.session["registration_otp_created_at"] = timezone.now().timestamp()

    request.session["registration_otp_expiry"] = expiry_seconds

    request.session["registration_otp_number"] = otp_number

    request.session["registration_otp_attempts"] = 0

    request.session["registration_email"] = email

    # New OTP means verification is not completed yet.
    request.session["email_verified"] = False

    # ==========================================
    # SEND EMAIL
    # ==========================================

    try:

        send_mail(
            "Campus Clans - Email Verification OTP",
            f"""
Your Campus Clans registration OTP is:

{otp}

This OTP expires in {expiry_seconds} seconds.

You have {
    OTP_MAX_SENDS_24_HOURS - sends_used - 1
} OTP request(s) remaining in the last 24 hours.

If you did not request this registration,
please ignore this email.
""",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )

    except Exception as e:
        print("OTP EMAIL ERROR:", repr(e))

        # Don't leave a usable OTP in the session
        request.session.pop("registration_otp", None)
        request.session.pop("registration_otp_created_at", None)
        request.session.pop("registration_otp_expiry", None)
        request.session.pop("registration_otp_number", None)
        request.session.pop("registration_otp_attempts", None)

        return JsonResponse(
            {"success": False, "error": ("Unable to send OTP. " "Please try again.")},
            status=500,
        )

    # ==========================================
    # RECORD SUCCESSFUL OTP SEND
    # ==========================================

    OTPRequestLog.objects.create(email=email, purpose="registration")

    sends_used += 1

    sends_remaining = OTP_MAX_SENDS_24_HOURS - sends_used

    # ==========================================
    # RESPONSE
    # ==========================================

    return JsonResponse(
        {
            "success": True,
            "message": ("OTP sent successfully."),
            "expires_in": expiry_seconds,
            "sends_remaining": sends_remaining,
            "otp_number": otp_number,
            "limit_reached": (sends_remaining == 0),
        }
    )


def verify_otp(request):

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    email = request.POST.get("email", "").strip().lower()
    entered_otp = request.POST.get("otp", "").strip()

    saved_otp = request.session.get("registration_otp")
    saved_email = request.session.get("registration_email")
    created_at = request.session.get("registration_otp_created_at")
    attempts = int(request.session.get("registration_otp_attempts", 0))

    if (
        not saved_otp
        or not saved_email
        or _otp_is_expired(created_at, OTP_RESEND_EXPIRY_SECONDS)
    ):
        _clear_registration_otp(request)
        return JsonResponse(
            {"success": False, "error": "OTP has expired or was not requested."},
            status=400,
        )

    if attempts >= OTP_MAX_ATTEMPTS:
        _clear_registration_otp(request)
        return JsonResponse(
            {
                "success": False,
                "error": "Too many incorrect attempts. Please request a new OTP.",
            },
            status=429,
        )

    if email != saved_email:
        return JsonResponse(
            {"success": False, "error": "Email does not match the OTP request."},
            status=400,
        )

    if entered_otp != saved_otp:
        attempts += 1
        request.session["registration_otp_attempts"] = attempts
        remaining = OTP_MAX_ATTEMPTS - attempts
        if remaining <= 0:
            _clear_registration_otp(request)
            return JsonResponse(
                {
                    "success": False,
                    "error": "Too many incorrect attempts. Please request a new OTP.",
                },
                status=429,
            )
        return JsonResponse(
            {
                "success": False,
                "error": f"Invalid OTP. {remaining} attempts remaining.",
            },
            status=400,
        )

    request.session["email_verified"] = True
    request.session["verified_email"] = saved_email
    _clear_registration_otp(request)

    return JsonResponse({"success": True, "message": "Email verified successfully."})


def register_student(request):

    if request.method != "POST":
        return redirect("register")

    name = request.POST.get("name", "").strip()
    department = request.POST.get("department", "").strip()
    branch = request.POST.get("branch", "").strip()
    email = request.POST.get("email", "").strip().lower()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")

    verified_email = request.session.get("verified_email")
    email_verified = request.session.get("email_verified", False)

    if not email_verified or not verified_email:

        return render(
            request,
            "signup.html",
            {"error": "Please verify your email before registering."},
        )

    if not all([name, department, branch, email, username, password, confirm_password]):

        return render(request, "signup.html", {"error": "Please fill in all fields."})

    if email != verified_email:

        return render(
            request,
            "signup.html",
            {"error": "The email address does not match the verified email."},
        )

    if password != confirm_password:

        return render(request, "signup.html", {"error": "Passwords do not match."})

    if len(password) < 8:

        return render(
            request,
            "signup.html",
            {"error": "Password must contain at least 8 characters."},
        )

    if User.objects.filter(username__iexact=username).exists():

        return render(
            request, "signup.html", {"error": "This username is already taken."}
        )

    if User.objects.filter(email__iexact=email).exists():

        return render(
            request, "signup.html", {"error": "This email is already registered."}
        )

    if StudentProfile.objects.filter(email__iexact=email).exists():

        return render(
            request, "signup.html", {"error": "This email is already registered."}
        )

    user = User.objects.create_user(username=username, email=email, password=password)

    StudentProfile.objects.create(
        user=user,
        name=name,
        department=department,
        branch=branch,
        email=email,
        email_verified=True,
    )

    request.session.pop("registration_otp", None)
    request.session.pop("registration_email", None)
    request.session.pop("email_verified", None)
    request.session.pop("verified_email", None)

    return render(
        request,
        "signup.html",
        {"message": "Registration successful. You can now login."},
    )


@login_required
def home(request):

    profile = StudentProfile.objects.filter(user=request.user).first()

    if not profile:
        logout(request)
        return redirect("login")

    membership = (
        ClanMember.objects.filter(student=profile).select_related("clan").first()
    )

    my_clan = membership.clan if membership else None

    clans = Clan.objects.all().order_by("-created_at")[:6]

    now = timezone.now()

    events = Event.objects.filter(end_date__gte=now).order_by("end_date")

    participations = EventParticipation.objects.filter(
        event_id__in=events.values("id")
    ).select_related("clan", "student")

    # as an individual
    student_participated_event_ids = set(
        participations.filter(
            participant_type="student",
            student=profile,
        ).values_list("event_id", flat=True)
    )

    clan_participated_event_ids = set()

    if my_clan:
        clan_participated_event_ids = set(
            participations.filter(
                participant_type="clan",
                clan=my_clan,
            ).values_list("event_id", flat=True)
        )

    is_clan_leader = bool(membership and membership.role in ["leader", "co_leader"])

    is_my_clan_suspended = False

    if my_clan:
        is_my_clan_suspended = ClanSuspension.objects.filter(
            clan=my_clan,
            is_active=True,
            end_date__gt=now,
        ).exists()

    return render(
        request,
        "user/home.html",
        {
            "profile": profile,
            "my_clan": my_clan,
            "membership": membership,
            "clans": clans,
            "events": events,
            # New event participation variables
            "student_participated_event_ids": student_participated_event_ids,
            "clan_participated_event_ids": clan_participated_event_ids,
            # Clan participation permissions
            "is_clan_leader": is_clan_leader,
            "is_my_clan_suspended": is_my_clan_suspended,
        },
    )


def student_dashboard(request):

    if not request.user.is_authenticated:
        return redirect("login")

    return redirect("home")


def logout_view(request):

    request.session.pop("is_admin", None)

    from django.contrib.auth import logout

    logout(request)

    return redirect("login")

@login_required
def view_profile(request, student_id):

    profile = get_object_or_404(
        StudentProfile.objects.select_related("user"), id=student_id
    )

    if profile.user_id == request.user.id:
        return redirect("profile")

    skills = StudentSkill.objects.filter(student=profile).select_related(
        "skill", "skill__skill_type"
    )

    highlighted_skills = skills.filter(is_highlighted=True)

    membership = (
        ClanMember.objects.filter(student=profile)
        .select_related("clan")
        .first()
    )

    my_clan = membership.clan if membership else None

    personal_projects = StudentProject.objects.filter(
        student=profile
    ).order_by("-created_at")

    clan_projects = (
        ClanProject.objects.filter(project_members__student=profile)
        .select_related("clan")
        .distinct()
        .order_by("-created_at")
    )

    viewer_membership = (
        ClanMember.objects.filter(student__user=request.user)
        .select_related("clan")
        .first()
    )

    pending_invitation = None

    if viewer_membership:

        pending_invitation = ClanInvitation.objects.filter(
            clan=viewer_membership.clan,
            invited_student=profile,
            status="pending"
        ).first()

    pending_join_request = None

    if viewer_membership:

        pending_join_request = ClanJoinRequest.objects.filter(
            clan=viewer_membership.clan,
            student=profile,
            status="pending"
        ).first()

    can_invite = (
        viewer_membership is not None
        and viewer_membership.role in ["leader", "co_leader"]
        and membership is None
        and not pending_invitation
        and not pending_join_request
    )

    can_manage_join_request = (
        viewer_membership is not None
        and viewer_membership.role in ["leader", "co_leader"]
        and pending_join_request is not None
    )

    # ==========================================
    # PRIVATE UPCOMING EVENT PARTICIPATION
    # ==========================================

    upcoming_events = []

    # Only members of the same clan can see
    # this student's upcoming event participation.
    same_clan = (
        viewer_membership
        and membership
        and viewer_membership.clan_id == membership.clan_id
    )

    if same_clan:

        upcoming_participations = (
            EventParticipation.objects
            .filter(
                student=profile,
                event__end_date__gte=timezone.now(),
            )
            .select_related("event")
            .order_by("event__end_date")
        )

        for participation in upcoming_participations:

            event = participation.event

            # Temporary attribute used only by the template
            event.participation_type = participation.participant_type

            upcoming_events.append(event)

    return render(
        request,
        "user/view_profile.html",
        {
            "profile": profile,
            "skills": skills,
            "highlighted_skills": highlighted_skills,
            "my_clan": my_clan,
            "personal_projects": personal_projects,
            "clan_projects": clan_projects,
            "viewer_membership": viewer_membership,
            "can_invite": can_invite,
            "pending_invitation": pending_invitation,
            "pending_join_request": pending_join_request,
            "can_manage_join_request": can_manage_join_request,

            # Private event participation
            "upcoming_events": upcoming_events,
            "can_view_upcoming_events": bool(same_clan),
        },
    )


@login_required
@block_suspended_student
def cancel_clan_invitation(request, invitation_id):

    if request.method != "POST":
        return redirect("profile")

    sender = get_object_or_404(StudentProfile, user=request.user)

    invitation = get_object_or_404(
        ClanInvitation.objects.select_related("clan", "invited_student"),
        id=invitation_id,
    )

    if invitation.invited_by_id != sender.id:
        return redirect("view_profile", student_id=invitation.invited_student_id)

    if invitation.status != "pending":
        return redirect("view_profile", student_id=invitation.invited_student_id)

    sender_membership = ClanMember.objects.filter(
        student=sender, clan=invitation.clan
    ).first()

    if not sender_membership:
        return redirect("view_profile", student_id=invitation.invited_student_id)

    # Only Leader and Co-Leader can cancel.
    if sender_membership.role not in ["leader", "co_leader"]:
        return redirect("view_profile", student_id=invitation.invited_student_id)

    invitation.status = "cancelled"
    invitation.responded_at = timezone.now()

    invitation.save(update_fields=["status", "responded_at"])

    return redirect("view_profile", student_id=invitation.invited_student_id)

@login_required
def profile_view(request):
    profile = get_object_or_404(StudentProfile, user=request.user)

    skills = StudentSkill.objects.filter(student=profile).select_related(
        "skill", "skill__skill_type"
    )
    highlighted_skills = skills.filter(is_highlighted=True)

    membership = (
        ClanMember.objects.filter(student=profile)
        .select_related("clan")
        .first()
    )
    my_clan = membership.clan if membership else None

    personal_projects = StudentProject.objects.filter(
        student=profile
    ).order_by("-created_at")

    clan_projects = (
        ClanProject.objects.filter(project_members__student=profile)
        .select_related("clan")
        .distinct()
        .order_by("-created_at")
    )

    clan_invitations = (
        ClanInvitation.objects.filter(
            invited_student=profile,
            status="pending"
        )
        .select_related("clan", "invited_by", "invited_by__user")
        .order_by("-created_at")
    )

    student_recruitment = StudentClanRecruitment.objects.filter(
        student=profile,
        expires_at__gt=timezone.now()
    ).first()

    admin_messages = AdminMessage.objects.filter(
        student=profile
    ).order_by("-created_at")

    # ==========================================
    # UPCOMING EVENT PARTICIPATION
    # ==========================================

    upcoming_event_participations = (
        EventParticipation.objects
        .filter(
            student=profile,
            event__end_date__gte=timezone.now(),
        )
        .select_related("event")
        .order_by("event__end_date")
    )

    upcoming_events = []

    for participation in upcoming_event_participations:
        event = participation.event

        # Used by the template to show whether
        # participation is individual or clan.
        event.participation_type = participation.participant_type

        upcoming_events.append(event)


    student_trophies = EventTrophy.objects.filter(student=profile).select_related("event").order_by("-awarded_at")

    return render(
        request,
        "user/profile.html",
        {
            "profile": profile,
            "skills": skills,
            "highlighted_skills": highlighted_skills,
            "my_clan": my_clan,
            "personal_projects": personal_projects,
            "clan_projects": clan_projects,
            "clan_invitations": clan_invitations,
            "student_recruitment": student_recruitment,
            "admin_messages": admin_messages,

            "student_trophies": student_trophies,
            "upcoming_events": upcoming_events,
        },
    )

@login_required
@block_suspended_student
def edit_profile(request):

    profile = StudentProfile.objects.get(user=request.user)

    skill_types = SkillType.objects.all()

    if request.method == "POST":

        # =========================
        # BASIC PROFILE DATA
        # =========================

        name = request.POST.get("name", "").strip()
        username = request.POST.get("username", "").strip()
        department = request.POST.get("department", "").strip()
        branch = request.POST.get("branch", "").strip()
        about = request.POST.get("about", "").strip()

        github = request.POST.get("github", "").strip()
        linkedin = request.POST.get("linkedin", "").strip()
        instagram = request.POST.get("instagram", "").strip()
        youtube = request.POST.get("youtube", "").strip()

        # =========================
        # SKILLS
        # =========================

        selected_skill_ids = request.POST.getlist("skills")
        highlighted_skill_ids = request.POST.getlist("highlighted_skills")

        # Maximum 35 selected skills
        if len(selected_skill_ids) > 35:
            return render(
                request,
                "user/edit_profile.html",
                {
                    "profile": profile,
                    "skill_types": skill_types,
                    "error": "You can select a maximum of 35 skills.",
                },
            )

        # Maximum 10 highlighted skills
        if len(highlighted_skill_ids) > 10:
            return render(
                request,
                "user/edit_profile.html",
                {
                    "profile": profile,
                    "skill_types": skill_types,
                    "error": "You can highlight a maximum of 10 skills.",
                },
            )

        # Highlighted skills must be selected skills
        if not set(highlighted_skill_ids).issubset(set(selected_skill_ids)):
            return render(
                request,
                "user/edit_profile.html",
                {
                    "profile": profile,
                    "skill_types": skill_types,
                    "error": "Highlighted skills must be selected skills.",
                },
            )

        # =========================
        # USERNAME VALIDATION
        # =========================

        if not username:
            messages.error(request, "Username cannot be empty.")
            return redirect("edit_profile")

        # Check whether another user already has this username
        username_exists = (
            User.objects.filter(username=username).exclude(id=request.user.id).exists()
        )

        if username_exists:
            messages.error(request, "This username is already taken.")
            return redirect("edit_profile")

        # =========================
        # EMAIL CHANGE / OTP
        # =========================

        verified_email = request.session.get("verified_new_email")

        email_change_verified = request.session.get("email_change_verified", False)

        if email_change_verified and verified_email:

            # Make sure this email is not already used
            email_exists = (
                StudentProfile.objects.filter(email=verified_email)
                .exclude(user=request.user)
                .exists()
            )

            if email_exists:
                return render(
                    request,
                    "user/edit_profile.html",
                    {
                        "profile": profile,
                        "skill_types": skill_types,
                        "error": "This email is already registered.",
                    },
                )

            # Update StudentProfile email
            profile.email = verified_email
            profile.email_verified = True

            # Update Django User email
            request.user.email = verified_email
            request.user.save(update_fields=["email"])

            # Clear email verification session
            request.session.pop("verified_new_email", None)
            request.session.pop("email_change_verified", None)

        # =========================
        # UPDATE USERNAME
        # =========================

        request.user.username = username
        request.user.save(update_fields=["username"])

        # =========================
        # UPDATE PROFILE
        # =========================

        profile.name = name
        profile.department = department
        profile.branch = branch
        profile.about = about

        profile.github = github
        profile.linkedin = linkedin
        profile.instagram = instagram
        profile.youtube = youtube

        # =========================
        # PROFILE PICTURE
        # =========================

        if "profile_picture" in request.FILES:

            old_profile_picture = profile.profile_picture

            profile.profile_picture = request.FILES["profile_picture"]

            # Delete old physical file
            delete_media_file(old_profile_picture)

        profile.save()

        # =========================
        # UPDATE STUDENT SKILLS
        # =========================

        StudentSkill.objects.filter(student=profile).delete()

        valid_skills = Skill.objects.filter(id__in=selected_skill_ids)

        highlighted_set = set(highlighted_skill_ids)

        for skill in valid_skills:

            StudentSkill.objects.create(
                student=profile,
                skill=skill,
                is_highlighted=str(skill.id) in highlighted_set,
            )

        # =========================
        # SUCCESS
        # =========================

        messages.success(request, "Profile updated successfully.")

        return redirect("profile")

    # =========================
    # GET REQUEST
    # =========================

    return render(
        request,
        "user/edit_profile.html",
        {
            "profile": profile,
            "skill_types": skill_types,
        },
    )


def get_skills(request, skill_type_id):
    skills = Skill.objects.filter(skill_type_id=skill_type_id).order_by("name")

    data = [{"id": skill.id, "name": skill.name} for skill in skills]

    return JsonResponse({"skills": data})


@block_suspended_student
def send_email_change_otp(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Login required."}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST request required."}, status=405)

    email = request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse({"error": "Email is required."}, status=400)

    if (
        StudentProfile.objects.filter(email__iexact=email)
        .exclude(user=request.user)
        .exists()
    ):
        return JsonResponse({"error": "This email is already registered."}, status=400)

    created_at = request.session.get("email_change_otp_created_at")

    if created_at:
        otp_number = request.session.get("registration_otp_number", 1)

        expiry_seconds = (
            OTP_FIRST_EXPIRY_SECONDS if otp_number == 1 else OTP_RESEND_EXPIRY_SECONDS
        )

        if not _otp_is_expired(created_at, expiry_seconds):
            remaining = max(
                1,
                expiry_seconds - int(timezone.now().timestamp() - float(created_at)),
            )

            return JsonResponse(
                {
                    "error": (f"OTP is still valid for " f"{remaining} seconds."),
                    "otp_active": True,
                    "remaining_seconds": remaining,
                },
                status=429,
            )

    otp = str(random.randint(100000, 999999))

    request.session["email_change_otp"] = otp
    request.session["email_change_otp_created_at"] = timezone.now().timestamp()
    request.session["email_change_otp_attempts"] = 0
    request.session["email_change_new_email"] = email
    request.session["email_change_verified"] = False

    try:
        send_mail(
            "Campus Clans - Email Verification",
            f"Your email verification OTP is: {otp}\n\nThis OTP expires in 40 seconds.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception:
        _clear_email_change_otp(request)
        request.session.pop("email_change_new_email", None)
        request.session["email_change_verified"] = False
        return JsonResponse(
            {"error": "Unable to send OTP. Please try again."}, status=500
        )

    return JsonResponse({"success": True, "message": "OTP sent successfully."})


@block_suspended_student
def verify_email_change_otp(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Login required."}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST request required."}, status=405)

    otp = request.POST.get("otp", "").strip()
    saved_otp = request.session.get("email_change_otp")
    saved_email = request.session.get("email_change_new_email")
    created_at = request.session.get("email_change_otp_created_at")
    attempts = int(request.session.get("email_change_otp_attempts", 0))

    if (
        not saved_otp
        or not saved_email
        or _otp_is_expired(created_at, OTP_RESEND_EXPIRY_SECONDS)
    ):
        _clear_email_change_otp(request)
        return JsonResponse(
            {"error": "OTP has expired or was not requested."}, status=400
        )

    if attempts >= OTP_MAX_ATTEMPTS:
        _clear_email_change_otp(request)
        return JsonResponse(
            {"error": "Too many incorrect attempts. Please request a new OTP."},
            status=429,
        )

    if otp != saved_otp:
        attempts += 1
        request.session["email_change_otp_attempts"] = attempts
        remaining = OTP_MAX_ATTEMPTS - attempts
        if remaining <= 0:
            _clear_email_change_otp(request)
            return JsonResponse(
                {"error": "Too many incorrect attempts. Please request a new OTP."},
                status=429,
            )
        return JsonResponse(
            {"error": f"Invalid OTP. {remaining} attempts remaining."}, status=400
        )

    request.session["email_change_verified"] = True
    request.session["verified_new_email"] = saved_email
    _clear_email_change_otp(request)

    return JsonResponse(
        {
            "success": True,
            "message": "Email verified successfully.",
            "email": saved_email,
        }
    )


# ============================================================
# PROJECTS
# ============================================================


@login_required
@block_suspended_student
def create_student_project(request):
    profile = get_object_or_404(StudentProfile, user=request.user)

    if request.method == "POST":

        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()

        images = request.FILES.getlist("images")

        # Separate project cover image
        cover_image = request.FILES.get("cover_image")

        # -----------------------------
        # VALIDATION
        # -----------------------------

        if not title:
            return render(
                request,
                "user/create_project.html",
                {"error": "Project title is required."},
            )

        if not description:
            return render(
                request,
                "user/create_project.html",
                {"error": "Project description is required."},
            )

        if not images:
            return render(
                request,
                "user/create_project.html",
                {"error": "At least one project image is required."},
            )

        # -----------------------------
        # MAX 2 ONGOING PROJECTS
        # -----------------------------

        ongoing_projects = StudentProject.objects.filter(
            student=profile, status="ongoing"
        ).count()

        if ongoing_projects >= 2:
            return render(
                request,
                "user/create_project.html",
                {
                    "error": (
                        "You can have a maximum of 2 ongoing projects. "
                        "Complete an existing project before creating another."
                    )
                },
            )

        # -----------------------------
        # CREATE PROJECT
        # -----------------------------

        project = StudentProject.objects.create(
            student=profile,
            title=title,
            description=description,
            cover_image=cover_image,
        )

        # -----------------------------
        # CREATE PROJECT STARTED UPDATE
        # -----------------------------

        initial_update = StudentProjectUpdate.objects.create(
            project=project, caption="Project started."
        )

        # -----------------------------
        # MOVE INITIAL IMAGES INTO
        # PROJECT STARTED UPDATE
        # -----------------------------

        for image in images:

            StudentProjectUpdateImage.objects.create(update=initial_update, image=image)

        # -----------------------------
        # PROJECT LINKS
        # -----------------------------

        labels = request.POST.getlist("link_label")
        urls = request.POST.getlist("link_url")

        for label, url in zip(labels, urls):

            label = label.strip()
            url = url.strip()

            if label and url:

                StudentProjectLink.objects.create(project=project, label=label, url=url)

        return redirect("student_project_detail", project_id=project.id)

    return render(request, "user/create_project.html")


@login_required
def student_project_detail(request, project_id):
    project = get_object_or_404(
        StudentProject.objects.select_related("student", "student__user"), id=project_id
    )

    links = project.links.all().order_by("created_at")

    updates = project.updates.prefetch_related("images").order_by("-created_at")

    return render(
        request,
        "user/project_detail.html",
        {
            "project": project,
            "links": links,
            "updates": updates,
            "is_owner": project.student.user_id == request.user.id,
        },
    )


@login_required
@block_suspended_student
def change_student_project_cover(request, project_id):
    project = get_object_or_404(
        StudentProject, id=project_id, student__user=request.user
    )

    if request.method != "POST":
        return redirect("student_project_detail", project_id=project.id)

    cover_image = request.FILES.get("cover_image")

    if not cover_image:
        return redirect("student_project_detail", project_id=project.id)

    # Delete old cover image physically
    if project.cover_image:
        project.cover_image.delete(save=False)

    # Save new cover
    project.cover_image = cover_image
    project.save(update_fields=["cover_image"])

    return redirect("student_project_detail", project_id=project.id)


@login_required
@block_suspended_student
def create_student_project_update(request, project_id):

    project = get_object_or_404(StudentProject, id=project_id)

    profile = get_object_or_404(StudentProfile, user=request.user)

    # Only project owner can add updates
    if project.student_id != profile.id:
        return redirect("student_project_detail", project_id=project.id)

    if request.method == "POST":

        caption = request.POST.get("caption", "").strip()

        images = request.FILES.getlist("images")

        if not caption:

            return render(
                request,
                "user/create_project_update.html",
                {
                    "project": project,
                    "error": "Update caption is required.",
                },
            )

        update = StudentProjectUpdate.objects.create(
            project=project,
            caption=caption,
        )

        # Multiple images are optional
        for image in images:

            StudentProjectUpdateImage.objects.create(
                update=update,
                image=image,
            )

        return redirect("student_project_detail", project_id=project.id)

    return render(request, "user/create_project_update.html", {"project": project})


@login_required
@block_suspended_student
def complete_student_project(request, project_id):

    if request.method != "POST":
        return redirect("student_project_detail", project_id=project_id)

    project = get_object_or_404(StudentProject, id=project_id)

    profile = get_object_or_404(StudentProfile, user=request.user)

    if project.student_id != profile.id:
        return redirect("student_project_detail", project_id=project.id)

    if project.status == "completed":
        return redirect("student_project_detail", project_id=project.id)

    project.status = "completed"
    project.completed_at = timezone.now()

    project.save(update_fields=["status", "completed_at", "updated_at"])

    return redirect("student_project_detail", project_id=project.id)


@login_required
@block_suspended_student
def create_clan_project(request, clan_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    # Only Leader / Co-Leader
    if not membership or membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)

    # Maximum 2 ongoing projects per clan
    if ClanProject.objects.filter(clan=clan, status="ongoing").count() >= 2:
        return render(
            request,
            "clans/create_project.html",
            {
                "clan": clan,
                "clan_members": ClanMember.objects.filter(clan=clan)
                .select_related("student", "student__user")
                .order_by("student__name"),
                "error": (
                    "This clan can have a maximum of 2 ongoing "
                    "projects. Complete an existing project "
                    "before creating another."
                ),
            },
        )

    clan_members = (
        ClanMember.objects.filter(clan=clan)
        .select_related("student", "student__user")
        .order_by("student__name")
    )

    if request.method == "POST":

        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()

        cover_image = request.FILES.get("cover_image")
        images = request.FILES.getlist("images")

        selected_member_ids = request.POST.getlist("project_members")

        selected_participant_ids = request.POST.getlist("initial_participants")

        # Validation
        if not title:
            return render(
                request,
                "clans/create_project.html",
                {
                    "clan": clan,
                    "clan_members": clan_members,
                    "error": "Project title is required.",
                },
            )

        if not description:
            return render(
                request,
                "clans/create_project.html",
                {
                    "clan": clan,
                    "clan_members": clan_members,
                    "error": "Project description is required.",
                },
            )

        if not images:
            return render(
                request,
                "clans/create_project.html",
                {
                    "clan": clan,
                    "clan_members": clan_members,
                    "error": "At least one project image is required.",
                },
            )

        if not selected_member_ids:
            return render(
                request,
                "clans/create_project.html",
                {
                    "clan": clan,
                    "clan_members": clan_members,
                    "error": "Please select at least one project member.",
                },
            )

        # Validate project members
        valid_member_ids = set(
            ClanMember.objects.filter(
                clan=clan, student_id__in=selected_member_ids
            ).values_list("student_id", flat=True)
        )

        selected_member_ids = {
            int(student_id)
            for student_id in selected_member_ids
            if student_id.isdigit()
        }

        if not selected_member_ids.issubset(valid_member_ids):
            return render(
                request,
                "clans/create_project.html",
                {
                    "clan": clan,
                    "clan_members": clan_members,
                    "error": "Invalid project member selection.",
                },
            )

        # Validate initial participants
        selected_participant_ids = {
            int(student_id)
            for student_id in selected_participant_ids
            if student_id.isdigit()
        }

        if not selected_participant_ids.issubset(selected_member_ids):
            return render(
                request,
                "clans/create_project.html",
                {
                    "clan": clan,
                    "clan_members": clan_members,
                    "error": (
                        "Project Started participants must "
                        "be selected project members."
                    ),
                },
            )

        # Create project
        project = ClanProject.objects.create(
            clan=clan, title=title, description=description, cover_image=cover_image
        )

        # Project members
        ClanProjectMember.objects.bulk_create(
            [
                ClanProjectMember(project=project, student_id=student_id)
                for student_id in selected_member_ids
            ],
            ignore_conflicts=True,
        )

        # Project links
        link_labels = request.POST.getlist("link_label[]")
        link_urls = request.POST.getlist("link_url[]")

        for label, url in zip(link_labels, link_urls):

            label = label.strip()
            url = url.strip()

            if label and url:
                ClanProjectLink.objects.create(project=project, label=label, url=url)

        # Project Started update
        initial_update = ClanProjectUpdate.objects.create(
            project=project, caption="Project started."
        )

        # Initial images
        for image in images:
            ClanProjectUpdateImage.objects.create(update=initial_update, image=image)

        # Initial participants
        project_members = {
            member.student_id: member
            for member in ClanProjectMember.objects.filter(project=project)
        }

        ClanProjectUpdateParticipant.objects.bulk_create(
            [
                ClanProjectUpdateParticipant(
                    update=initial_update, project_member=project_members[student_id]
                )
                for student_id in selected_participant_ids
                if student_id in project_members
            ],
            ignore_conflicts=True,
        )

        return redirect("clan_project_detail", project_id=project.id)

    return render(
        request,
        "clans/create_project.html",
        {"clan": clan, "clan_members": clan_members},
    )


@login_required
def clan_project_detail(request, project_id):

    project = get_object_or_404(
        ClanProject.objects.select_related("clan"),
        id=project_id,
    )

    links = project.links.order_by("created_at")

    updates = project.updates.prefetch_related(
        "images",
        "participants__project_member__student",
    ).order_by("-created_at")

    members = project.project_members.select_related(
        "student", "student__user"
    ).order_by("joined_project_at")

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    membership = ClanMember.objects.filter(
        clan=project.clan,
        student=profile,
    ).first()

    can_manage = membership is not None and membership.role in [
        "leader",
        "co_leader",
    ]

    return render(
        request,
        "clans/project_detail.html",
        {
            "project": project,
            "links": links,
            "updates": updates,
            "members": members,
            "can_manage": can_manage,
        },
    )


@login_required
@block_suspended_student
def create_clan_project_update(request, project_id):

    project = get_object_or_404(
        ClanProject.objects.select_related("clan"),
        id=project_id,
    )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    membership = ClanMember.objects.filter(
        clan=project.clan,
        student=profile,
    ).first()

    # Only Leader / Co-Leader can create updates
    if not membership or membership.role not in [
        "leader",
        "co_leader",
    ]:
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    # Only members already assigned to this project
    # can participate in updates.
    project_members = (
        ClanProjectMember.objects.filter(project=project)
        .select_related("student", "student__user")
        .order_by("joined_project_at")
    )

    if request.method == "POST":

        caption = request.POST.get("caption", "").strip()

        selected_participant_ids = request.POST.getlist("participants")

        if not caption:
            return render(
                request,
                "clans/create_project_update.html",
                {
                    "project": project,
                    "project_members": project_members,
                    "error": "Update caption is required.",
                },
            )

        # Convert submitted IDs to integers
        participant_ids = {
            int(member_id)
            for member_id in selected_participant_ids
            if member_id.isdigit()
        }

        # IDs that are actually members of this project
        valid_project_member_ids = set(
            project_members.values_list(
                "id",
                flat=True,
            )
        )

        # Prevent users from submitting arbitrary
        # ClanProjectMember IDs belonging to another project.
        if not participant_ids.issubset(valid_project_member_ids):
            return render(
                request,
                "clans/create_project_update.html",
                {
                    "project": project,
                    "project_members": project_members,
                    "error": "Invalid participant selection.",
                },
            )

        # Create the update
        update = ClanProjectUpdate.objects.create(
            project=project,
            caption=caption,
        )

        # Save update images
        for image in request.FILES.getlist("images"):
            ClanProjectUpdateImage.objects.create(
                update=update,
                image=image,
            )

        # Save update participants
        ClanProjectUpdateParticipant.objects.bulk_create(
            [
                ClanProjectUpdateParticipant(
                    update=update,
                    project_member_id=member_id,
                )
                for member_id in participant_ids
            ],
            ignore_conflicts=True,
        )

        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    return render(
        request,
        "clans/create_project_update.html",
        {
            "project": project,
            "project_members": project_members,
        },
    )


@login_required
@block_suspended_student
def complete_clan_project(request, project_id):
    if request.method != "POST":
        return redirect(
            "clan_project_detail",
            project_id=project_id,
        )

    project = get_object_or_404(
        ClanProject.objects.select_related("clan"),
        id=project_id,
    )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    membership = ClanMember.objects.filter(
        clan=project.clan,
        student=profile,
    ).first()

    if not membership or membership.role not in ["leader", "co_leader"]:
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    if project.status == "completed":
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    project.status = "completed"
    project.completed_at = timezone.now()

    project.save(
        update_fields=[
            "status",
            "completed_at",
            "updated_at",
        ]
    )

    return redirect(
        "clan_project_detail",
        project_id=project.id,
    )


def mark_admin_message_read(request, message_id):
    if not request.user.is_authenticated:
        return redirect("login")

    message = get_object_or_404(AdminMessage, id=message_id, student__user=request.user)

    if request.method == "POST":
        message.is_read = True
        message.save(update_fields=["is_read"])

    return redirect("profile")


@login_required
@block_suspended_student
def delete_clan_project(request, project_id):
    if request.method != "POST":
        return redirect(
            "clan_project_detail",
            project_id=project_id,
        )

    project = get_object_or_404(
        ClanProject.objects.select_related("clan"),
        id=project_id,
    )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    membership = ClanMember.objects.filter(
        clan=project.clan,
        student=profile,
    ).first()

    if not membership or membership.role not in ["leader", "co_leader"]:
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    if project.cover_image:
        project.cover_image.delete(save=False)

    for image_obj in project.images.all():
        if image_obj.image:
            image_obj.image.delete(save=False)

    for update in project.updates.prefetch_related("images"):
        for image_obj in update.images.all():

            if image_obj.image:
                image_obj.image.delete(save=False)

    clan_id = project.clan.id

    project.delete()

    return redirect(
        "clan_profile",
        clan_id=clan_id,
    )


@login_required
@block_suspended_student
def change_clan_project_cover(request, project_id):

    if request.method != "POST":
        return redirect(
            "clan_project_detail",
            project_id=project_id,
        )

    project = get_object_or_404(
        ClanProject.objects.select_related("clan"),
        id=project_id,
    )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    membership = ClanMember.objects.filter(
        clan=project.clan,
        student=profile,
    ).first()

    if not membership or membership.role not in [
        "leader",
        "co_leader",
    ]:
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    cover_image = request.FILES.get("cover_image")

    if not cover_image:
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    # -------------------------------------------------
    # Delete old cover from storage
    # -------------------------------------------------

    if project.cover_image:
        project.cover_image.delete(save=False)

    # -------------------------------------------------
    # Save new cover
    # -------------------------------------------------

    project.cover_image = cover_image

    project.save(
        update_fields=[
            "cover_image",
            "updated_at",
        ]
    )

    return redirect(
        "clan_project_detail",
        project_id=project.id,
    )


@login_required
@block_suspended_student
def delete_clan_project_update(request, update_id):
    if request.method != "POST":
        return redirect("home")

    update = get_object_or_404(
        ClanProjectUpdate.objects.select_related("project__clan"),
        id=update_id,
    )

    project = update.project

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    membership = ClanMember.objects.filter(
        clan=project.clan,
        student=profile,
    ).first()

    if not membership or membership.role not in ["leader", "co_leader"]:
        return redirect(
            "clan_project_detail",
            project_id=project.id,
        )

    # Physically delete update image files.
    for image_obj in update.images.all():
        if image_obj.image:
            image_obj.image.delete(save=False)

    update.delete()

    return redirect(
        "clan_project_detail",
        project_id=project.id,
    )


@login_required
@block_suspended_student
def create_clan_post_page(request, clan_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    membership = ClanMember.objects.filter(clan=clan, student=profile).first()

    print("DEBUG PROFILE:", profile)
    print("DEBUG CLAN:", clan)
    print("DEBUG MEMBERSHIP:", membership)

    if membership:
        print("DEBUG ROLE:", membership.role)

    if not membership:
        return HttpResponse("You are not a member of this clan.")

    if membership.role not in ["leader", "co_leader"]:
        return HttpResponse(
            f"You are not allowed to create posts. Your role is: {membership.role}"
        )

    return render(request, "clans/create_post.html", {"clan": clan})


@login_required
def clan_posts(request, clan_id):

    clan = get_object_or_404(Clan, id=clan_id)

    posts = (
        ClanPost.objects.filter(clan=clan)
        .select_related("author", "author__user")
        .prefetch_related("images", "likes")
        .order_by("-created_at")
    )

    student = get_object_or_404(StudentProfile, user=request.user)

    liked_post_ids = set(
        ClanPostLike.objects.filter(student=student, post__clan=clan).values_list(
            "post_id", flat=True
        )
    )

    membership = ClanMember.objects.filter(clan=clan, student=student).first()

    is_member = membership is not None

    can_manage_clan_content = membership is not None and membership.role in [
        "leader",
        "co_leader",
    ]

    editable_post_ids = set()

    if can_manage_clan_content:

        edit_cutoff = timezone.now() - timedelta(days=7)

        editable_post_ids = set(
            posts.filter(created_at__gt=edit_cutoff).values_list("id", flat=True)
        )

    return render(
        request,
        "clans/clan_posts.html",
        {
            "clan": clan,
            "posts": posts,
            "student": student,
            "liked_post_ids": liked_post_ids,
            "membership": membership,
            "is_member": is_member,
            "can_manage_clan_content": can_manage_clan_content,
            "editable_post_ids": editable_post_ids,
        },
    )

def participate_in_event(request, event_id, participation_type):
    denied = block_suspended_student(request)

    if denied:
        return denied

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "message": "POST request required.",
            },
            status=405,
        )

    event = get_object_or_404(Event, id=event_id)

    now = timezone.now()

    # ---------------------------------
    # EVENT ALREADY ENDED
    # ---------------------------------

    if now >= event.end_date:
        return JsonResponse(
            {
                "success": False,
                "message": "This event has already ended.",
            },
            status=400,
        )

    # ---------------------------------
    # VALID PARTICIPATION TYPE
    # ---------------------------------

    if participation_type not in ["student", "clan"]:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid participation type.",
            },
            status=400,
        )

    # ---------------------------------
    # CHECK EVENT PARTICIPANT TYPE
    # ---------------------------------

    if (
        event.participant_type != "both"
        and event.participant_type != participation_type
    ):
        return JsonResponse(
            {
                "success": False,
                "message": "This event does not allow this type of participation.",
            },
            status=400,
        )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user,
    )

    # =================================
    # INDIVIDUAL STUDENT PARTICIPATION
    # =================================

    if participation_type == "student":

        existing = EventParticipation.objects.filter(
            event=event,
            participant_type="student",
            student=profile,
        ).first()

        if existing:
            return JsonResponse(
                {
                    "success": False,
                    "message": "You are already participating individually.",
                    "already_participating": True,
                    "participant_type": "student",
                },
                status=400,
            )

        EventParticipation.objects.create(
            event=event,
            participant_type="student",
            student=profile,
        )

        return JsonResponse(
            {
                "success": True,
                "message": "You joined the event successfully.",
                "participant_type": "student",
                "participating": True,
            }
        )


    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    if not membership:
        return JsonResponse(
            {
                "success": False,
                "message": "You are not a member of any clan.",
            },
            status=400,
        )

    if membership.role not in ["leader", "co_leader"]:
        return JsonResponse(
            {
                "success": False,
                "message": "Only the clan leader or co-leader can register the clan.",
            },
            status=403,
        )

    clan = membership.clan

    # ---------------------------------
    # SUSPENDED CLAN
    # ---------------------------------

    if clan_is_suspended(clan):
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Your clan is suspended and cannot "
                    "participate in events."
                ),
            },
            status=403,
        )


    existing = EventParticipation.objects.filter(
        event=event,
        participant_type="clan",
        clan=clan,
    ).first()

    if existing:
        return JsonResponse(
            {
                "success": False,
                "message": "Your clan is already participating in this event.",
                "already_participating": True,
                "participant_type": "clan",
                "selection_editable": (
                    now < event.end_date - timedelta(hours=24)
                ),
            },
            status=400,
        )


    selection_cutoff = event.end_date - timedelta(hours=24)

    inside_final_24_hours = now >= selection_cutoff


    if inside_final_24_hours:
        return JsonResponse(
            {
                "success": False,
                "requires_representatives": True,
                "participant_type": "clan",
                "message": (
                    "Because the event ends within 24 hours, "
                    "you must select your clan representatives now. "
                    "They cannot be changed after confirmation."
                ),
            },
            status=409,
        )

    participation = EventParticipation.objects.create(
        event=event,
        participant_type="clan",
        clan=clan,
        student=profile,
    )

    return JsonResponse(
        {
            "success": True,
            "message": "Your clan joined the event successfully.",
            "participant_type": "clan",
            "participating": True,
            "selection_editable": True,
            "participation_id": participation.id,
        }
    )

@login_required
@block_suspended_student
def event_clan_members(request, event_id):

    if request.method != "GET":
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request method."
            },
            status=405
        )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    event = get_object_or_404(
        Event,
        id=event_id
    )

    # Find current clan membership
    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    if not membership:
        return JsonResponse(
            {
                "success": False,
                "message": "You are not a member of any clan."
            },
            status=400
        )

    # Only leader/co-leader can manage representatives
    if membership.role not in ["leader", "co_leader"]:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Only the clan leader or co-leader "
                    "can select clan representatives."
                )
            },
            status=403
        )

    clan = membership.clan

    # Suspended clan cannot participate
    if clan_is_suspended(clan):
        return JsonResponse(
            {
                "success": False,
                "message": "Your clan is currently suspended."
            },
            status=403
        )

    # Check whether clan participation is allowed
    if event.participant_type not in ["clan", "both"]:
        return JsonResponse(
            {
                "success": False,
                "message": "Clan participation is not allowed for this event."
            },
            status=400
        )

    # Get CURRENT clan members
    clan_members = (
        ClanMember.objects
        .filter(clan=clan)
        .select_related("student", "student__user")
        .order_by("student__name")
    )

    # Find existing clan participation
    participation = (
        EventParticipation.objects
        .filter(
            event=event,
            clan=clan,
            participant_type="clan"
        )
        .first()
    )

    selected_member_ids = []

    if participation:
        selected_member_ids = list(
            EventClanParticipant.objects
            .filter(participation=participation)
            .values_list("student_id", flat=True)
        )

    members = []

    for member in clan_members:

        student = member.student

        members.append({
            "id": student.id,
            "name": student.name or student.user.username,
            "username": student.user.username,
            "role": member.role,
            "selected": student.id in selected_member_ids,
        })

    # 24-hour editing deadline
    selection_deadline = event.end_date - timedelta(hours=24)

    editing_locked = timezone.now() >= selection_deadline

    return JsonResponse(
        {
            "success": True,
            "event": {
                "id": event.id,
                "name": event.name,
                "end_date": event.end_date.isoformat(),
            },
            "clan": {
                "id": clan.id,
                "name": clan.name,
            },
            "members": members,
            "participating": participation is not None,
            "editing_locked": editing_locked,
            "selected_member_ids": selected_member_ids,
        }
    )

@login_required
@block_suspended_student
def select_event_clan_members(request, event_id):

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request method."
            },
            status=405
        )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    event = get_object_or_404(
        Event,
        id=event_id
    )

    now = timezone.now()

    # --------------------------------------------------
    # EVENT MUST NOT HAVE ENDED
    # --------------------------------------------------

    if now >= event.end_date:
        return JsonResponse(
            {
                "success": False,
                "message": "This event has already ended."
            },
            status=400
        )

    # --------------------------------------------------
    # MEMBER EDIT DEADLINE
    # --------------------------------------------------

    if not event.participant_edit_window_open:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "The clan representative list is locked. "
                    "Members can only be changed until 24 hours "
                    "before the event ends."
                )
            },
            status=400
        )

    # --------------------------------------------------
    # CURRENT CLAN MEMBERSHIP
    # --------------------------------------------------

    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    if not membership:
        return JsonResponse(
            {
                "success": False,
                "message": "You are not a member of any clan."
            },
            status=400
        )

    if membership.role not in ["leader", "co_leader"]:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Only the clan leader or co-leader "
                    "can select event participants."
                )
            },
            status=403
        )

    clan = membership.clan

    if clan_is_suspended(clan):
        return JsonResponse(
            {
                "success": False,
                "message": "Your clan is currently suspended."
            },
            status=403
        )

    # --------------------------------------------------
    # FIND CLAN EVENT PARTICIPATION
    # --------------------------------------------------

    participation = get_object_or_404(
        EventParticipation,
        event=event,
        participant_type="clan",
        clan=clan,
    )

    # --------------------------------------------------
    # GET SELECTED STUDENT IDS
    # --------------------------------------------------

    try:
        data = json.loads(request.body)
        selected_ids = data.get("student_ids", [])

    except (json.JSONDecodeError, TypeError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid member selection data."
            },
            status=400
        )

    if not isinstance(selected_ids, list):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid member selection."
            },
            status=400
        )

    # Convert to integers and remove duplicates
    try:
        selected_ids = list(
            dict.fromkeys(
                int(student_id)
                for student_id in selected_ids
            )
        )
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid student IDs."
            },
            status=400
        )

    # --------------------------------------------------
    # AT LEAST ONE MEMBER
    # --------------------------------------------------

    if not selected_ids:
        return JsonResponse(
            {
                "success": False,
                "message": "Select at least one clan member."
            },
            status=400
        )

    # --------------------------------------------------
    # CURRENT CLAN MEMBERS
    # --------------------------------------------------

    current_member_ids = set(
        ClanMember.objects.filter(
            clan=clan
        ).values_list(
            "student_id",
            flat=True
        )
    )

    # --------------------------------------------------
    # PREVIOUSLY SELECTED MEMBERS
    #
    # These are allowed to remain even if they later
    # leave the clan because they already represented
    # the clan in this event.
    # --------------------------------------------------

    existing_selected_ids = set(
        EventClanParticipant.objects.filter(
            participation=participation
        ).values_list(
            "student_id",
            flat=True
        )
    )

    allowed_ids = (
        current_member_ids |
        existing_selected_ids
    )

    invalid_ids = set(selected_ids) - allowed_ids

    if invalid_ids:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "One or more selected students are not "
                    "current members of your clan."
                )
            },
            status=400
        )

    # --------------------------------------------------
    # SAVE SELECTION
    # --------------------------------------------------

    with transaction.atomic():

        EventClanParticipant.objects.filter(
            participation=participation
        ).exclude(
            student_id__in=selected_ids
        ).delete()

        existing_ids = set(
            EventClanParticipant.objects.filter(
                participation=participation,
                student_id__in=selected_ids,
            ).values_list(
                "student_id",
                flat=True
            )
        )

        new_participants = []

        for student_id in selected_ids:

            if student_id not in existing_ids:

                new_participants.append(
                    EventClanParticipant(
                        participation=participation,
                        student_id=student_id,
                    )
                )

        if new_participants:
            EventClanParticipant.objects.bulk_create(
                new_participants
            )

    return JsonResponse(
        {
            "success": True,
            "message": "Clan event participants have been updated.",
            "selected_count": len(selected_ids),
        }
    )

@login_required
@block_suspended_student
def cancel_event_participation(request, event_id):

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request method."
            },
            status=405
        )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    event = get_object_or_404(
        Event,
        id=event_id
    )

    if timezone.now() >= event.end_date:
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Participation can no longer be cancelled "
                    "because the event has ended."
                )
            },
            status=400
        )

    # --------------------------------------------------
    # INDIVIDUAL PARTICIPATION
    # --------------------------------------------------

    individual = EventParticipation.objects.filter(
        event=event,
        participant_type="student",
        student=profile,
    ).first()

    if individual:
        individual.delete()

        return JsonResponse(
            {
                "success": True,
                "participation_type": "student",
                "message": "Your participation has been cancelled."
            }
        )

    # --------------------------------------------------
    # CLAN PARTICIPATION
    # --------------------------------------------------

    membership = (
        ClanMember.objects
        .filter(student=profile)
        .select_related("clan")
        .first()
    )

    if (
        membership
        and membership.role in ["leader", "co_leader"]
    ):

        clan_participation = EventParticipation.objects.filter(
            event=event,
            participant_type="clan",
            clan=membership.clan,
        ).first()

        if clan_participation:

            clan_participation.delete()

            return JsonResponse(
                {
                    "success": True,
                    "participation_type": "clan",
                    "message": "Your clan's participation has been cancelled."
                }
            )

    return JsonResponse(
        {
            "success": False,
            "message": "You are not participating in this event."
        },
        status=400
    )
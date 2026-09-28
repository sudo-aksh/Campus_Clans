from django.contrib.auth import logout
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .models import StudentProfile, Skill, StudentSkill, SkillType, Clan, ClanMember, ClanInvitation, ClanJoinRequest, ClanPost, ClanPostLike, ClanStory,   ClanStoryView, ClanRecruitment, ClanRecruitmentSkill, ClanLeaveRequest, StudentClanRecruitment
from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
import random
from functools import wraps
from django.db.models import Q, Count

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


@login_required
def create_clan_post(request, clan_id):
    if request.method != "POST":
        return redirect("clan_profile", clan_id=clan_id)
    student = get_object_or_404(StudentProfile, user=request.user)
    clan = get_object_or_404(Clan, id=clan_id)
    membership = ClanMember.objects.filter(clan=clan, student=student).first()
    # Only Leader and Co-Leader can create posts
    if not membership or membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)
    content = request.POST.get("content", "").strip()
    caption = request.POST.get("caption", "").strip()
    image = request.FILES.get("image")

    if not content and not image:
        return redirect("clan_profile", clan_id=clan.id)

    ClanPost.objects.create(clan=clan, author=student, content=content, image=image, caption=caption)
    return redirect("clan_profile", clan_id=clan.id)

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.session.get("is_admin"):
            return redirect("login")

        return view_func(request, *args, **kwargs)

    return wrapper


@login_required
def global_recruitments(request):

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    now = timezone.now()

    # Remove expired student recruitment posts
    StudentClanRecruitment.objects.filter(
        expires_at__lte=now
    ).delete()

    # ---------------------------------------------------------
    # CURRENT USER'S CLAN MEMBERSHIP
    # ---------------------------------------------------------

    current_membership = (
        ClanMember.objects
        .select_related("clan")
        .filter(student=profile)
        .first()
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
        ClanRecruitment.objects
        .filter(expires_at__gt=now)
        .select_related(
            "clan",
            "created_by"
        )
        .prefetch_related(
            "fields",
            "required_skills__skill"
        )
        .order_by("-created_at")
    )

    # Current student's skills
    student_skill_ids = set(
        StudentSkill.objects
        .filter(student=profile)
        .values_list("skill_id", flat=True)
    )

    recruitment_data = []

    for recruitment in recruitments:

        # -----------------------------------------------------
        # SKILL MATCHING
        # -----------------------------------------------------

        required_skills = list(
            recruitment.required_skills.all()
        )

        required_skill_ids = {
            item.skill_id
            for item in required_skills
        }

        matched_skill_ids = (
            student_skill_ids & required_skill_ids
        )

        matched_skills = [
            item.skill
            for item in required_skills
            if item.skill_id in matched_skill_ids
        ]

        total_required = len(required_skills)

        match_count = len(matched_skills)

        match_percentage = (
            round(
                (match_count / total_required) * 100
            )
            if total_required
            else 0
        )

        # -----------------------------------------------------
        # CURRENT USER'S JOIN REQUEST
        # -----------------------------------------------------

        existing_request = (
            ClanJoinRequest.objects
            .filter(
                clan=recruitment.clan,
                student=profile,
                status="pending"
            )
            .first()
        )

        # -----------------------------------------------------
        # CURRENT USER ALREADY A MEMBER?
        # -----------------------------------------------------

        is_member = ClanMember.objects.filter(
            clan=recruitment.clan,
            student=profile
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
        StudentClanRecruitment.objects
        .filter(
            expires_at__gt=now
        )
        .select_related(
            "student",
            "student__user"
        )
        .prefetch_related(
            "student__student_skills__skill__skill_type"
        )
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



@login_required
def student_clan_recruitments(request):
    """
    Show all active student clan recruitment posts.
    """

    # Clean up expired recruitments whenever this page is opened
    StudentClanRecruitment.objects.filter(
        expires_at__lte=timezone.now()
    ).delete()

    recruitments = (
        StudentClanRecruitment.objects
        .select_related("student", "student__user")
        .filter(expires_at__gt=timezone.now())
        .order_by("-created_at")
    )

    current_student = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    # Student's own active recruitment
    own_recruitment = StudentClanRecruitment.objects.filter(
        student=current_student,
        expires_at__gt=timezone.now()
    ).first()

    return render(
        request,
        "clans/student_recruitments.html",
        {
            "recruitments": recruitments,
            "own_recruitment": own_recruitment,
            "current_student": current_student,
        }
    )


@login_required
def create_student_clan_recruitment(request):

    student = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    # Student cannot create recruitment if already in a clan
    if ClanMember.objects.filter(student=student).exists():
        return redirect("student_clan_recruitments")

    # Remove expired recruitment first
    StudentClanRecruitment.objects.filter(
        student=student,
        expires_at__lte=timezone.now()
    ).delete()

    # Only one active recruitment per student
    if StudentClanRecruitment.objects.filter(
        student=student,
        expires_at__gt=timezone.now()
    ).exists():
        return redirect("student_clan_recruitments")

    if request.method == "POST":

        message = request.POST.get("message", "").strip()

        if not message:
            return redirect("student_clan_recruitments")

        StudentClanRecruitment.objects.create(
            student=student,
            message=message,
            expires_at=timezone.now() + timedelta(days=7)
        )

        return redirect("student_clan_recruitments")

    return redirect("student_clan_recruitments")


@login_required
def delete_student_clan_recruitment(request, recruitment_id):

    student = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    recruitment = get_object_or_404(
        StudentClanRecruitment,
        id=recruitment_id,
        student=student
    )

    if request.method == "POST":
        recruitment.delete()

    return redirect("student_clan_recruitments")

@login_required
def invite_student_to_clan(request, recruitment_id):

    student = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    recruitment = get_object_or_404(
        StudentClanRecruitment.objects.select_related("student"),
        id=recruitment_id,
        expires_at__gt=timezone.now()
    )

    clan_member = get_object_or_404(
        ClanMember.objects.select_related("clan"),
        student=student
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
        clan=clan,
        invited_student=target_student,
        status="pending"
    ).exists():
        return redirect("student_clan_recruitments")

    ClanInvitation.objects.create(
        clan=clan,
        invited_student=target_student,
        invited_by=student,
        status="pending"
    )

    return redirect("student_clan_recruitments")

@login_required
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
def delete_clan_post(request, post_id):

    if request.method != "POST":
        return redirect("home")

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=profile).first()

    # User must belong to the clan
    if not membership:
        return redirect("clan_profile", clan_id=post.clan_id)

    # Only Leader and Co-Leader can delete
    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=post.clan_id)

    clan_id = post.clan_id

    post.delete()

    return redirect("clan_profile", clan_id=clan_id)

@login_required
def edit_clan_recruitment(request, recruitment_id):
    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )
    recruitment = get_object_or_404(
        ClanRecruitment.objects.select_related("clan", "created_by"),
        id=recruitment_id
    )
    clan = recruitment.clan
    membership = ClanMember.objects.filter(
        clan=clan,
        student=profile
    ).first()
    if not membership:
        return redirect("clan_profile", clan_id=clan.id)
    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)
    if recruitment.expires_at <= timezone.now():
        return redirect("clan_profile", clan_id=clan.id)
    skill_types = SkillType.objects.all()
    selected_field_ids = set(
        recruitment.fields.values_list("id", flat=True)
    )
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
        ClanRecruitmentSkill.objects.filter(
            recruitment=recruitment
        ).delete()
        ClanRecruitmentSkill.objects.bulk_create(
            [
                ClanRecruitmentSkill(
                    recruitment=recruitment,
                    skill=skill
                )
                for skill in skills
            ]
        )
        return redirect(
            "clan_profile",
            clan_id=clan.id
        )
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
def delete_clan_recruitment(request, recruitment_id):
    if request.method != "POST":
        return redirect("home")
    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )
    recruitment = get_object_or_404(
        ClanRecruitment.objects.select_related("clan"),
        id=recruitment_id
    )
    clan = recruitment.clan
    membership = ClanMember.objects.filter(
        clan=clan,
        student=profile
    ).first()
    if not membership:
        return redirect("clan_profile", clan_id=clan.id)
    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=clan.id)
    recruitment.delete()
    return redirect(
        "clan_profile",
        clan_id=clan.id
    )

@login_required
def edit_clan_post(request, post_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=post.clan_id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=post.clan_id)

    if request.method == "POST":

        content = request.POST.get("content", "").strip()

        caption = request.POST.get("caption", "").strip()

        post.content = content
        post.caption = caption

        post.save(update_fields=["content", "caption", "updated_at"])

        return redirect("clan_profile", clan_id=post.clan_id)

    return render(request, "clans/edit_post.html", {"post": post})


@login_required
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
def clan_story_viewers(request, story_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(
        ClanStory.objects.select_related("clan", "author"), id=story_id
    )

    membership = ClanMember.objects.filter(clan=story.clan, student=profile).first()

    if not membership:
        return redirect("clan_profile", clan_id=story.clan_id)

    if membership.role not in ["leader", "co_leader"]:
        return redirect("clan_profile", clan_id=story.clan_id)

    viewers = (
        ClanStoryView.objects.filter(story=story)
        .select_related("student", "student__user")
        .order_by("-viewed_at")
    )

    return render(
        request,
        "clans/story_viewers.html",
        {
            "story": story,
            "viewers": viewers,
        },
    )


@login_required
def toggle_clan_post_like(request, post_id):

    if request.method != "POST":
        return redirect("home")

    student = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    existing_like = ClanPostLike.objects.filter(post=post, student=student).first()

    if existing_like:

        existing_like.delete()

    else:

        ClanPostLike.objects.create(post=post, student=student)

    return redirect("clan_profile", clan_id=post.clan.id)


@login_required
def view_clan_story(request, story_id):

    student = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory.objects.select_related("clan"), id=story_id)

    if story.expires_at <= timezone.now():

        return redirect("clan_profile", clan_id=story.clan.id)

    ClanStoryView.objects.get_or_create(story=story, student=student)

    return render(request, "clans/view_story.html", {"story": story})


@login_required
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

    story.delete()

    return redirect("clan_profile", clan_id=clan_id)


@login_required
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
def clan_post_likes(request, post_id):

    student = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=student).first()

    if not membership:
        return redirect("clan_profile", clan_id=post.clan.id)

    likes = (
        ClanPostLike.objects.filter(post=post)
        .select_related("student", "student__user")
        .order_by("-created_at")
    )

    return render(
        request,
        "clans/post_likes.html",
        {
            "post": post,
            "likes": likes,
        },
    )


@login_required
def clan_story_viewers(request, story_id):

    student = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(ClanStory.objects.select_related("clan"), id=story_id)

    membership = ClanMember.objects.filter(clan=story.clan, student=student).first()

    if not membership:
        return redirect("clan_profile", clan_id=story.clan.id)

    viewers = (
        ClanStoryView.objects.filter(story=story)
        .select_related("student", "student__user")
        .order_by("-viewed_at")
    )

    return render(
        request,
        "clans/story_viewers.html",
        {
            "story": story,
            "viewers": viewers,
        },
    )


@login_required
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

    ClanMember.objects.create(clan=clan, student=student, role="member")

    invitation.status = "accepted"
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "responded_at"])

    return redirect("profile")


@login_required
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


    ClanMember.objects.create(clan=clan, student=join_request.student, role="member")


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

        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")


        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            request.session["is_admin"] = True

            return redirect("admin_dashboard")


        user = authenticate(request, username=username, password=password)

        if user is not None:

            login(request, user)

            return redirect("home")


        return render(
            request, "signup.html", {"error": "Invalid username or password."}
        )

    return render(request, "signup.html")


def register_view(request):

    return render(request, "signup.html")


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
            .filter(clan_membership__isnull=True)
            .select_related("user")
            .order_by("name")[:10]
        )

        students = [
            {
                "id": student.id,
                "name": student.name,
                "username": student.user.username,
                "department": student.department,
                "profile_picture": (
                    student.profile_picture.url if student.profile_picture else None
                ),
            }
            for student in results
        ]

    return JsonResponse({"students": students})


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


@login_required
def create_clan(request):

    profile = get_object_or_404(StudentProfile, user=request.user)


    if ClanMember.objects.filter(student=profile).exists():
        return redirect("home")

    if request.method == "POST":

        name = request.POST.get("name", "").strip()

        speciality = request.POST.get("speciality", "").strip()

        profile_description = request.POST.get("profile_description", "").strip()

        description = request.POST.get("description", "").strip()

        # New search-box field
        selected_student_id = request.POST.get("member", "").strip()


        if not name:
            return render(
                request, "clans/create_clans.html", {"error": "Clan name is required."}
            )

        if not speciality:
            return render(
                request, "clans/create_clans.html", {"error": "Speciality is required."}
            )

        if len(profile_description) > 50:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("Profile description must be " "50 characters or less.")},
            )

        word_count = len(description.split())

        if word_count > 250:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("Clan description must be " "250 words or less.")},
            )

        if not selected_student_id:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("Please search and select " "one student for your clan.")},
            )


        selected_student = get_object_or_404(StudentProfile, id=selected_student_id)

        if selected_student.id == profile.id:
            return render(
                request,
                "clans/create_clans.html",
                {"error": ("You cannot select yourself " "as the second member.")},
            )


        if ClanMember.objects.filter(student=selected_student).exists():

            return render(
                request,
                "clans/create_clans.html",
                {"error": ("This student is already " "a member of another clan.")},
            )


        if Clan.objects.filter(name__iexact=name).exists():

            return render(
                request,
                "clans/create_clans.html",
                {"error": ("A clan with this name " "already exists.")},
            )


        clan = Clan.objects.create(
            name=name,
            speciality=speciality,
            profile_description=profile_description,
            description=description,
            created_by=profile,
            logo=request.FILES.get("logo"),
            banner=request.FILES.get("banner"),
        )


        ClanMember.objects.create(clan=clan, student=profile, role="leader")

        ClanMember.objects.create(clan=clan, student=selected_student, role="co_leader")

        return redirect("clan_profile", clan_id=clan.id)


    return render(request, "clans/create_clans.html")


@login_required
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
            clan.logo = request.FILES.get("logo")

        if request.FILES.get("banner"):
            clan.banner = request.FILES.get("banner")

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
def reject_clan_leave_request(request, request_id):

    if request.method != "POST":
        return redirect("profile")

    approver = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    leave_request = get_object_or_404(
        ClanLeaveRequest.objects.select_related(
            "clan"
        ),
        id=request_id
    )

    if leave_request.status != "pending":
        return redirect("profile")

    clan = leave_request.clan

    approver_membership = ClanMember.objects.filter(
        clan=clan,
        student=approver
    ).first()

    if not approver_membership:
        return redirect("profile")

    if approver_membership.role not in [
        "leader",
        "co_leader"
    ]:
        return redirect("profile")

    leave_request.status = "rejected"
    leave_request.responded_at = timezone.now()

    leave_request.save(
        update_fields=[
            "status",
            "responded_at"
        ]
    )

    return redirect(
        "clan_profile",
        clan_id=clan.id
    )

@login_required
def accept_clan_leave_request(request, request_id):

    if request.method != "POST":
        return redirect("profile")

    approver = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    leave_request = get_object_or_404(
        ClanLeaveRequest.objects.select_related(
            "clan",
            "student"
        ),
        id=request_id
    )

    if leave_request.status != "pending":
        return redirect("profile")

    clan = leave_request.clan

    approver_membership = ClanMember.objects.filter(
        clan=clan,
        student=approver
    ).first()

    if not approver_membership:
        return redirect("profile")

    # Leader or Co-Leader only
    if approver_membership.role not in [
        "leader",
        "co_leader"
    ]:
        return redirect("profile")

    if leave_request.student_id == approver.id:
        return redirect(
            "clan_profile",
            clan_id=clan.id
        )

    member = ClanMember.objects.filter(
        clan=clan,
        student=leave_request.student
    ).first()

    if not member:
        leave_request.status = "cancelled"
        leave_request.responded_at = timezone.now()
        leave_request.save(
            update_fields=[
                "status",
                "responded_at"
            ]
        )

        return redirect(
            "clan_profile",
            clan_id=clan.id
        )

    if member.role == "leader":
        return redirect(
            "clan_profile",
            clan_id=clan.id
        )

    member.delete()

    leave_request.status = "accepted"
    leave_request.responded_at = timezone.now()

    leave_request.save(
        update_fields=[
            "status",
            "responded_at"
        ]
    )

    if ClanMember.objects.filter(
        clan=clan
    ).count() < 2:

        clan.delete()

        return redirect("home")

    return redirect(
        "clan_profile",
        clan_id=clan.id
    )

@login_required
def request_clan_leave(request, clan_id):

    if request.method != "POST":
        return redirect(
            "clan_profile",
            clan_id=clan_id
        )

    student = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    clan = get_object_or_404(
        Clan,
        id=clan_id
    )

    membership = ClanMember.objects.filter(
        clan=clan,
        student=student
    ).first()

    if not membership:
        return redirect(
            "clan_profile",
            clan_id=clan.id
        )

    if membership.role == "leader":
        return redirect(
            "clan_profile",
            clan_id=clan.id
        )

    existing_request = ClanLeaveRequest.objects.filter(
        clan=clan,
        student=student,
        status="pending"
    ).exists()

    if existing_request:
        return redirect(
            "clan_profile",
            clan_id=clan.id
        )

    ClanLeaveRequest.objects.create(
        clan=clan,
        student=student
    )

    return redirect(
        "clan_profile",
        clan_id=clan.id
    )

@login_required
def remove_clan_member(request, clan_id, member_id):

    if request.method != "POST":
        return redirect("edit_clan", clan_id=clan_id)

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    clan = get_object_or_404(
        Clan,
        id=clan_id
    )

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    member = get_object_or_404(
        ClanMember,
        id=member_id,
        clan=clan
    )

    if member.student_id == clan.created_by_id:
        return redirect("edit_clan", clan_id=clan.id)

    if member.role == "co_leader":
        return redirect("edit_clan", clan_id=clan.id)

    member.delete()

    if ClanMember.objects.filter(clan=clan).count() < 2:
        clan.delete()
        return redirect("home")

    return redirect(
        "edit_clan",
        clan_id=clan.id
    )

@login_required
def delete_clan(request, clan_id):

    profile = StudentProfile.objects.get(user=request.user)

    clan = get_object_or_404(Clan, id=clan_id)

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    if request.method == "POST":

        clan.delete()

        return redirect("home")

    return redirect("edit_clan", clan_id=clan.id)

@login_required
def change_clan_member_role(request, clan_id, member_id):

    if request.method != "POST":
        return redirect("edit_clan", clan_id=clan_id)

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    clan = get_object_or_404(
        Clan,
        id=clan_id
    )

    if clan.created_by_id != profile.id:
        return redirect("clan_profile", clan_id=clan.id)

    member = get_object_or_404(
        ClanMember,
        id=member_id,
        clan=clan
    )

    if member.student_id == clan.created_by_id:
        return redirect("edit_clan", clan_id=clan.id)

    role = request.POST.get("role")

    if role not in ["member", "co_leader"]:
        return redirect("edit_clan", clan_id=clan.id)

    if role == "co_leader":

        existing_co_leader = ClanMember.objects.filter(
            clan=clan,
            role="co_leader"
        ).exclude(
            id=member.id
        ).exists()

        if existing_co_leader:
            return redirect("edit_clan", clan_id=clan.id)

    member.role = role
    member.save(update_fields=["role"])

    return redirect(
        "edit_clan",
        clan_id=clan.id
    )

@login_required
def clan_profile(request, clan_id):

    clan = get_object_or_404(
        Clan,
        id=clan_id
    )

    profile = get_object_or_404(
        StudentProfile,
        user=request.user
    )

    members = (
        ClanMember.objects
        .filter(clan=clan)
        .select_related(
            "student",
            "student__user"
        )
        .order_by("-role", "joined_at")
    )

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

    is_creator = (
        clan.created_by_id == profile.id
    )

    pending_join_request = (
        ClanJoinRequest.objects
        .filter(
            clan=clan,
            student=profile,
            status="pending"
        )
        .first()
    )

    pending_invitation = (
        ClanInvitation.objects
        .filter(
            clan=clan,
            invited_student=profile,
            status="pending"
        )
        .first()
    )

    can_manage_join_requests = (
        is_member
        and membership.role in [
            "leader",
            "co_leader"
        ]
    )

    can_manage_clan_content = (
        is_member
        and membership.role in [
            "leader",
            "co_leader"
        ]
    )

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

    member_count = members.count()

    clan_full = (
        member_count >= 12
    )

    can_join = (
        not is_member
        and membership is None
        and not pending_join_request
        and not pending_invitation
        and not clan_full
    )

    pending_leave_request = (
        ClanLeaveRequest.objects
        .filter(
            clan=clan,
            student=profile,
            status="pending"
        )
        .first()
    )

    can_request_leave = (
        is_member
        and membership.role != "leader"
        and not pending_leave_request
    )

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

    story_cutoff = (
        timezone.now()
        - timedelta(hours=24)
    )

    stories = (
        ClanStory.objects
        .filter(
            clan=clan,
            created_at__gte=story_cutoff
        )
        .select_related(
            "author",
            "author__user"
        )
        .annotate(
            viewer_count=Count("views")
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

    active_recruitments = (
        ClanRecruitment.objects
        .filter(
            clan=clan,
            expires_at__gt=timezone.now()
        )
        .prefetch_related(
            "fields",
            "required_skills__skill"
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "clans/clan_profile.html",
        {
            "clan": clan,
            "members": members,

            "is_member": is_member,
            "is_creator": is_creator,
            "membership": membership,

            "member_count": member_count,
            "clan_full": clan_full,

            "pending_join_request": pending_join_request,
            "pending_invitation": pending_invitation,
            "can_join": can_join,

            "can_manage_join_requests": can_manage_join_requests,
            "join_requests": join_requests,

            "pending_leave_request": pending_leave_request,
            "can_request_leave": can_request_leave,
            "leave_requests": leave_requests,

            "can_manage_clan_content": can_manage_clan_content,

            "stories": stories,
            "viewed_story_ids": viewed_story_ids,

            "posts": posts,
            "liked_post_ids": liked_post_ids,

            "active_recruitments": active_recruitments,
        },
    )

@login_required
def create_clan_story(request, clan_id):

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

    caption = request.POST.get("caption", "").strip()

    image = request.FILES.get("image")

    if not content and not image:

        return redirect("clan_profile", clan_id=clan.id)

    ClanStory.objects.create(
        clan=clan, author=profile, content=content, caption=caption, image=image
    )

    return redirect("clan_profile", clan_id=clan.id)


@login_required
def view_clan_story(request, story_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    story = get_object_or_404(
        ClanStory.objects.select_related("clan", "author", "author__user"), id=story_id
    )

    if story.is_expired:

        return redirect("clan_profile", clan_id=story.clan_id)

    ClanStoryView.objects.get_or_create(story=story, student=profile)

    return render(request, "clans/view_story.html", {"story": story})


@login_required
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

    caption = request.POST.get("caption", "").strip()

    image = request.FILES.get("image")

    if not content and not image:

        return redirect("clan_profile", clan_id=clan.id)

    ClanPost.objects.create(
        clan=clan, author=profile, content=content, caption=caption, image=image
    )

    return redirect("clan_profile", clan_id=clan.id)


@login_required
def toggle_clan_post_like(request, post_id):

    if request.method != "POST":
        return redirect("home")

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost, id=post_id)

    like = ClanPostLike.objects.filter(post=post, student=profile).first()

    if like:
        like.delete()

    else:
        ClanPostLike.objects.create(post=post, student=profile)

    return redirect("clan_profile", clan_id=post.clan_id)


@login_required
def clan_post_likes(request, post_id):

    profile = get_object_or_404(StudentProfile, user=request.user)

    post = get_object_or_404(ClanPost.objects.select_related("clan"), id=post_id)

    membership = ClanMember.objects.filter(clan=post.clan, student=profile).first()

    if not membership:

        return redirect("clan_profile", clan_id=post.clan_id)

    likes = (
        ClanPostLike.objects.filter(post=post)
        .select_related("student", "student__user")
        .order_by("-created_at")
    )

    return render(request, "clans/post_likes.html", {"post": post, "likes": likes})


def send_otp(request):

    if request.method != "POST":

        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    # Get email from frontend

    email = request.POST.get("email", "").strip().lower()


    if not email:

        return JsonResponse(
            {"success": False, "error": "Email address is required."}, status=400
        )


    if User.objects.filter(email__iexact=email).exists():

        return JsonResponse(
            {"success": False, "error": "This email is already registered."}, status=400
        )


    otp = str(random.randint(100000, 999999))


    request.session["registration_otp"] = otp

    request.session["registration_email"] = email

    # Email is not verified yet

    request.session["email_verified"] = False


    try:

        send_mail(
            subject="Campus Clans - Email Verification OTP",
            message=f"""
Hello,

Your Campus Clans email verification OTP is:

{otp}

Please enter this OTP on the registration page to verify your email.

If you did not request this registration, please ignore this email.

Regards,
Campus Clans
""",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

    except Exception as e:

        print("EMAIL ERROR:", e)

        return JsonResponse(
            {"success": False, "error": "Unable to send OTP. Please try again."},
            status=500,
        )

    return JsonResponse({"success": True, "message": "OTP sent successfully."})



def verify_otp(request):

    if request.method != "POST":

        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)


    email = request.POST.get("email", "").strip().lower()

    entered_otp = request.POST.get("otp", "").strip()

    saved_otp = request.session.get("registration_otp")

    saved_email = request.session.get("registration_email")

    if not saved_otp:

        return JsonResponse(
            {"success": False, "error": "OTP has expired or was not requested."},
            status=400,
        )


    if email != saved_email:

        return JsonResponse(
            {"success": False, "error": "Email does not match the OTP request."},
            status=400,
        )


    if entered_otp != saved_otp:

        return JsonResponse({"success": False, "error": "Invalid OTP."}, status=400)


    request.session["email_verified"] = True

    request.session["verified_email"] = saved_email

    # OTP is no longer needed

    request.session.pop("registration_otp", None)


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

    clans = (
        Clan.objects
        .all()
        .order_by("-created_at")[:6]
    )

    return render(
        request,
        "user/home.html",
        {
            "profile": profile,
            "my_clan": my_clan,
            "clans": clans,
        },
    )


def admin_dashboard(request):

    if not request.session.get("is_admin"):
        return redirect("login")

    now = timezone.now()

    total_students = StudentProfile.objects.count()
    total_clans = Clan.objects.count()
    total_clan_members = ClanMember.objects.count()
    total_posts = ClanPost.objects.count()
    total_stories = ClanStory.objects.count()

    active_recruitments = ClanRecruitment.objects.filter(
        expires_at__gt=now
    ).count()

    pending_join_requests = ClanJoinRequest.objects.filter(
        status="pending"
    ).count()

    pending_invitations = ClanInvitation.objects.filter(
        status="pending"
    ).count()

    pending_leave_requests = ClanLeaveRequest.objects.filter(
        status="pending"
    ).count()

    recent_students = (
        StudentProfile.objects
        .select_related("user")
        .order_by("-created_at")[:5]
    )

    recent_clans = (
        Clan.objects
        .select_related("created_by", "created_by__user")
        .annotate(member_count=Count("members"))
        .order_by("-created_at")[:5]
    )

    recent_join_requests = (
        ClanJoinRequest.objects
        .select_related(
            "clan",
            "student",
            "student__user"
        )
        .order_by("-created_at")[:5]
    )

    top_clans = (
        Clan.objects
        .annotate(member_count=Count("members"))
        .order_by("-member_count", "name")[:5]
    )

    context = {
        "total_students": total_students,
        "total_clans": total_clans,
        "total_clan_members": total_clan_members,
        "total_posts": total_posts,
        "total_stories": total_stories,

        "active_recruitments": active_recruitments,
        "pending_join_requests": pending_join_requests,
        "pending_invitations": pending_invitations,
        "pending_leave_requests": pending_leave_requests,

        "recent_students": recent_students,
        "recent_clans": recent_clans,
        "recent_join_requests": recent_join_requests,
        "top_clans": top_clans,
    }

    return render(
        request,
        "admin/admin_dashboard.html",
        context
    )

@admin_required
def admin_recruitments(request):

    recruitments = (
        ClanRecruitment.objects
        .select_related(
            "clan",
            "created_by",
            "created_by__user",
        )
        .prefetch_related(
            "fields",
            "recruitment_skills__skill",
        )
        .order_by("-created_at")
    )

    search = request.GET.get("search", "").strip()

    if search:
        recruitments = recruitments.filter(
            Q(title__icontains=search)
            | Q(clan__name__icontains=search)
            | Q(description__icontains=search)
        )

    status_filter = request.GET.get("status", "").strip()

    if status_filter == "active":
        recruitments = [
            recruitment
            for recruitment in recruitments
            if recruitment.is_active
        ]

    elif status_filter == "expired":
        recruitments = [
            recruitment
            for recruitment in recruitments
            if not recruitment.is_active
        ]

    total_recruitments = ClanRecruitment.objects.count()

    active_recruitments = sum(
        1
        for recruitment in ClanRecruitment.objects.all()
        if recruitment.is_active
    )

    expired_recruitments = (
        total_recruitments - active_recruitments
    )

    context = {
        "recruitments": recruitments,
        "total_recruitments": total_recruitments,
        "active_recruitments": active_recruitments,
        "expired_recruitments": expired_recruitments,
        "search": search,
        "status_filter": status_filter,
    }

    return render(
        request,
        "admin/recruitments.html",
        context
    )

def student_dashboard(request):

    if not request.user.is_authenticated:
        return redirect("login")

    return render(request, "student_dashboard.html")

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
        ClanMember.objects.filter(student=profile).select_related("clan").first()
    )

    my_clan = membership.clan if membership else None


    viewer_membership = (
        ClanMember.objects.filter(student__user=request.user)
        .select_related("clan")
        .first()
    )


    pending_invitation = None

    if viewer_membership:

        pending_invitation = ClanInvitation.objects.filter(
            clan=viewer_membership.clan, invited_student=profile, status="pending"
        ).first()

    pending_join_request = None

    if viewer_membership:

        pending_join_request = ClanJoinRequest.objects.filter(
            clan=viewer_membership.clan, student=profile, status="pending"
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


    return render(
        request,
        "user/view_profile.html",
        {
            "profile": profile,
            "skills": skills,
            "highlighted_skills": highlighted_skills,
            "my_clan": my_clan,
            "viewer_membership": viewer_membership,
            "can_invite": can_invite,
            "pending_invitation": pending_invitation,
            "pending_join_request": pending_join_request,
            "can_manage_join_request": can_manage_join_request,
        },
    )


@login_required
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
        ClanMember.objects.filter(student=profile).select_related("clan").first()
    )

    my_clan = membership.clan if membership else None

    clan_invitations = (
        ClanInvitation.objects.filter(invited_student=profile, status="pending")
        .select_related("clan", "invited_by", "invited_by__user")
        .order_by("-created_at")
    )

    student_recruitment = StudentClanRecruitment.objects.filter(
        student=profile,
        expires_at__gt=timezone.now()
    ).first()

    return render(
        request,
        "user/profile.html",
        {
            "profile": profile,
            "skills": skills,
            "highlighted_skills": highlighted_skills,
            "my_clan": my_clan,
            "clan_invitations": clan_invitations,
            "student_recruitment": student_recruitment,
        },
    )


@login_required
def edit_profile(request):

    profile = StudentProfile.objects.get(user=request.user)

    skill_types = SkillType.objects.all()

    if request.method == "POST":

        name = request.POST.get("name", "").strip()
        department = request.POST.get("department", "").strip()
        branch = request.POST.get("branch", "").strip()
        about = request.POST.get("about", "").strip()

        github = request.POST.get("github", "").strip()
        linkedin = request.POST.get("linkedin", "").strip()
        instagram = request.POST.get("instagram", "").strip()
        youtube = request.POST.get("youtube", "").strip()

        selected_skill_ids = request.POST.getlist("skills")
        highlighted_skill_ids = request.POST.getlist("highlighted_skills")


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


        verified_email = request.session.get("verified_new_email")

        email_change_verified = request.session.get("email_change_verified", False)

        if email_change_verified and verified_email:

            # Make sure this email is still not used
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

            profile.email = verified_email
            profile.email_verified = True

            # Also update Django User email
            request.user.email = verified_email
            request.user.save(update_fields=["email"])

            # Clear email verification session
            request.session.pop("verified_new_email", None)

            request.session.pop("email_change_verified", None)


        profile.name = name
        profile.department = department
        profile.branch = branch
        profile.about = about

        profile.github = github
        profile.linkedin = linkedin
        profile.instagram = instagram
        profile.youtube = youtube

        # Profile picture
        if "profile_picture" in request.FILES:
            profile.profile_picture = request.FILES["profile_picture"]

        profile.save()


        StudentSkill.objects.filter(student=profile).delete()

        valid_skills = Skill.objects.filter(id__in=selected_skill_ids)

        highlighted_set = set(highlighted_skill_ids)

        for skill in valid_skills:

            StudentSkill.objects.create(
                student=profile,
                skill=skill,
                is_highlighted=str(skill.id) in highlighted_set,
            )

        return redirect("profile")

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


def send_email_change_otp(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Login required."}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST request required."}, status=405)

    email = request.POST.get("email", "").strip().lower()

    if not email:
        return JsonResponse({"error": "Email is required."}, status=400)

    if StudentProfile.objects.filter(email=email).exclude(user=request.user).exists():
        return JsonResponse({"error": "This email is already registered."}, status=400)

    otp = str(random.randint(100000, 999999))

    request.session["email_change_otp"] = otp
    request.session["email_change_new_email"] = email
    request.session["email_change_verified"] = False

    send_mail(
        "Campus Clans - Email Verification",
        f"Your email verification OTP is: {otp}\n\n"
        "This OTP is valid for this email-change request.",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )

    return JsonResponse({"success": True, "message": "OTP sent successfully."})


def verify_email_change_otp(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Login required."}, status=401)

    if request.method != "POST":
        return JsonResponse({"error": "POST request required."}, status=405)

    otp = request.POST.get("otp", "").strip()

    saved_otp = request.session.get("email_change_otp")

    saved_email = request.session.get("email_change_new_email")

    if not saved_otp or not saved_email:
        return JsonResponse(
            {"error": "No email verification request found."}, status=400
        )

    if otp != saved_otp:
        return JsonResponse({"error": "Invalid OTP."}, status=400)

    request.session["email_change_verified"] = True
    request.session["verified_new_email"] = saved_email

    request.session.pop("email_change_otp", None)

    return JsonResponse(
        {
            "success": True,
            "message": "Email verified successfully.",
            "email": saved_email,
        }
    )

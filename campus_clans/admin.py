from django.contrib import admin

from .models import (
    StudentProfile,
    SkillType,
    Skill,
    StudentSkill,
    Clan,
    ClanMember,
    ClanInvitation,
    ClanJoinRequest,
    ClanLeaveRequest,
    ClanPost,
    ClanPostLike,
    ClanStory,
    ClanStoryView,
    ClanRecruitment,
    ClanRecruitmentSkill,
    StudentClanRecruitment,
)


# ============================================================
# STUDENT PROFILE
# ============================================================

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "user",
        "email",
        "department",
        "branch",
        "email_verified",
        "created_at",
    )

    search_fields = (
        "name",
        "email",
        "user__username",
        "department",
        "branch",
    )

    list_filter = (
        "department",
        "branch",
        "email_verified",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# SKILL TYPE
# ============================================================

@admin.register(SkillType)
class SkillTypeAdmin(admin.ModelAdmin):

    list_display = (
        "name",
    )

    search_fields = (
        "name",
    )

    ordering = (
        "name",
    )


# ============================================================
# SKILL
# ============================================================

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "skill_type",
    )

    search_fields = (
        "name",
        "skill_type__name",
    )

    list_filter = (
        "skill_type",
    )

    ordering = (
        "skill_type",
        "name",
    )


# ============================================================
# STUDENT SKILL
# ============================================================

@admin.register(StudentSkill)
class StudentSkillAdmin(admin.ModelAdmin):

    list_display = (
        "student",
        "skill",
        "is_highlighted",
    )

    search_fields = (
        "student__name",
        "student__user__username",
        "skill__name",
    )

    list_filter = (
        "is_highlighted",
        "skill__skill_type",
    )


# ============================================================
# CLAN
# ============================================================

@admin.register(Clan)
class ClanAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "speciality",
        "created_by",
        "created_at",
    )

    search_fields = (
        "name",
        "speciality",
        "profile_description",
        "description",
        "created_by__name",
        "created_by__user__username",
    )

    list_filter = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN MEMBER
# ============================================================

@admin.register(ClanMember)
class ClanMemberAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "student",
        "role",
        "joined_at",
    )

    search_fields = (
        "clan__name",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "role",
        "joined_at",
    )

    ordering = (
        "-joined_at",
    )


# ============================================================
# CLAN INVITATION
# ============================================================

@admin.register(ClanInvitation)
class ClanInvitationAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "invited_student",
        "invited_by",
        "status",
        "created_at",
        "responded_at",
    )

    search_fields = (
        "clan__name",
        "invited_student__name",
        "invited_student__user__username",
        "invited_by__name",
        "invited_by__user__username",
    )

    list_filter = (
        "status",
        "created_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN JOIN REQUEST
# ============================================================

@admin.register(ClanJoinRequest)
class ClanJoinRequestAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "student",
        "request_type",
        "recruitment",
        "status",
        "created_at",
        "responded_at",
    )

    search_fields = (
        "clan__name",
        "student__name",
        "student__user__username",
        "recruitment__title",
    )

    list_filter = (
        "request_type",
        "status",
        "created_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN LEAVE REQUEST
# ============================================================

@admin.register(ClanLeaveRequest)
class ClanLeaveRequestAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "student",
        "status",
        "created_at",
        "responded_at",
    )

    search_fields = (
        "clan__name",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "status",
        "created_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN POST
# ============================================================

@admin.register(ClanPost)
class ClanPostAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "author",
        "caption",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "clan__name",
        "author__name",
        "author__user__username",
        "content",
        "caption",
    )

    list_filter = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN POST LIKE
# ============================================================

@admin.register(ClanPostLike)
class ClanPostLikeAdmin(admin.ModelAdmin):

    list_display = (
        "post",
        "student",
        "created_at",
    )

    search_fields = (
        "post__clan__name",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN STORY
# ============================================================

@admin.register(ClanStory)
class ClanStoryAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "author",
        "caption",
        "created_at",
        "is_expired",
    )

    search_fields = (
        "clan__name",
        "author__name",
        "author__user__username",
        "content",
        "caption",
    )

    list_filter = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN STORY VIEW
# ============================================================

@admin.register(ClanStoryView)
class ClanStoryViewAdmin(admin.ModelAdmin):

    list_display = (
        "story",
        "student",
        "viewed_at",
    )

    search_fields = (
        "story__clan__name",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "viewed_at",
    )

    ordering = (
        "-viewed_at",
    )


# ============================================================
# CLAN RECRUITMENT
# ============================================================

@admin.register(ClanRecruitment)
class ClanRecruitmentAdmin(admin.ModelAdmin):

    list_display = (
        "clan",
        "title",
        "created_by",
        "created_at",
        "expires_at",
        "is_active",
    )

    search_fields = (
        "clan__name",
        "title",
        "description",
        "created_by__name",
        "created_by__user__username",
    )

    list_filter = (
        "created_at",
        "expires_at",
    )

    filter_horizontal = (
        "fields",
    )

    ordering = (
        "-created_at",
    )


# ============================================================
# CLAN RECRUITMENT SKILL
# ============================================================

@admin.register(ClanRecruitmentSkill)
class ClanRecruitmentSkillAdmin(admin.ModelAdmin):

    list_display = (
        "recruitment",
        "skill",
    )

    search_fields = (
        "recruitment__title",
        "recruitment__clan__name",
        "skill__name",
    )

    list_filter = (
        "skill__skill_type",
    )
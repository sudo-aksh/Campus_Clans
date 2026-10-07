from django.contrib import admin
from django.contrib.auth.models import User

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
    ClanPostImage,
    ClanPostLike,
    ClanRecruitment,
    ClanRecruitmentSkill,
    StudentClanRecruitment,
    StudentProject,
    StudentProjectLink,
    StudentProjectImage,
    StudentProjectUpdate,
    StudentProjectUpdateImage,
    OTPRequestLog,
    ClanProject,
    ClanProjectMember,
    ClanProjectLink,
    ClanProjectImage,
    ClanProjectUpdate,
    ClanProjectUpdateImage,
    ClanProjectUpdateParticipant,
    ClanStory,
    ClanStoryView,
    ClanStoryLike,
)

# =========================================================
# STUDENT PROFILE
# =========================================================


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "username",
        "email",
        "email_verified",
        "department",
        "branch",
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
        "email_verified",
        "department",
        "branch",
        "created_at",
    )

    ordering = ("-created_at",)

    readonly_fields = ("created_at",)

    autocomplete_fields = ("user",)

    fieldsets = (
        (
            "Account",
            {
                "fields": (
                    "user",
                    "name",
                    "email",
                    "email_verified",
                )
            },
        ),
        (
            "Academic Information",
            {
                "fields": (
                    "department",
                    "branch",
                )
            },
        ),
        (
            "Profile",
            {
                "fields": (
                    "about",
                    "profile_picture",
                    "github",
                    "linkedin",
                    "instagram",
                    "youtube",
                )
            },
        ),
        (
            "System Information",
            {"fields": ("created_at",)},
        ),
    )

    def username(self, obj):
        return obj.user.username

    username.short_description = "Username"
    username.admin_order_field = "user__username"


# =========================================================
# SKILLS
# =========================================================


@admin.register(SkillType)
class SkillTypeAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "skill_count",
    )

    search_fields = ("name",)

    ordering = ("name",)

    def skill_count(self, obj):
        return obj.skills.count()

    skill_count.short_description = "Skills"


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "skill_type",
        "student_count",
    )

    search_fields = (
        "name",
        "skill_type__name",
    )

    list_filter = ("skill_type",)

    ordering = (
        "skill_type",
        "name",
    )

    autocomplete_fields = ("skill_type",)

    def student_count(self, obj):
        return obj.student_skills.count()

    student_count.short_description = "Students"


@admin.register(StudentSkill)
class StudentSkillAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "student",
        "skill",
        "skill_type",
        "is_highlighted",
    )

    search_fields = (
        "student__name",
        "student__user__username",
        "skill__name",
        "skill__skill_type__name",
    )

    list_filter = (
        "is_highlighted",
        "skill__skill_type",
    )

    autocomplete_fields = (
        "student",
        "skill",
    )

    def skill_type(self, obj):
        return obj.skill.skill_type.name

    skill_type.short_description = "Skill Type"


# =========================================================
# CLAN
# =========================================================


class ClanMemberInline(admin.TabularInline):
    model = ClanMember
    extra = 0
    autocomplete_fields = ("student",)
    readonly_fields = ("joined_at",)


@admin.register(Clan)
class ClanAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "name",
        "speciality",
        "created_by",
        "member_count",
        "post_count",
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
        "speciality",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = ("created_by",)

    readonly_fields = ("created_at",)

    inlines = (ClanMemberInline,)

    fieldsets = (
        (
            "Clan Information",
            {
                "fields": (
                    "name",
                    "logo",
                    "banner",
                    "speciality",
                    "profile_description",
                    "description",
                )
            },
        ),
        (
            "Ownership",
            {"fields": ("created_by",)},
        ),
        (
            "System Information",
            {"fields": ("created_at",)},
        ),
    )

    def member_count(self, obj):
        return obj.members.count()

    member_count.short_description = "Members"

    def post_count(self, obj):
        return obj.posts.count()

    post_count.short_description = "Posts"


# =========================================================
# CLAN MEMBER
# =========================================================


@admin.register(ClanMember)
class ClanMemberAdmin(admin.ModelAdmin):

    list_display = (
        "id",
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
        "clan",
        "joined_at",
    )

    ordering = ("-joined_at",)

    autocomplete_fields = (
        "clan",
        "student",
    )

    readonly_fields = ("joined_at",)


# =========================================================
# CLAN INVITATIONS
# =========================================================


@admin.action(description="Mark selected invitations as cancelled")
def cancel_invitations(modeladmin, request, queryset):
    queryset.update(status="cancelled")


@admin.action(description="Mark selected invitations as rejected")
def reject_invitations(modeladmin, request, queryset):
    queryset.update(status="rejected")


@admin.register(ClanInvitation)
class ClanInvitationAdmin(admin.ModelAdmin):

    list_display = (
        "id",
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
        "responded_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = (
        "clan",
        "invited_student",
        "invited_by",
    )

    readonly_fields = ("created_at",)

    actions = (
        cancel_invitations,
        reject_invitations,
    )


# =========================================================
# CLAN JOIN REQUESTS
# =========================================================


@admin.action(description="Accept selected join requests")
def accept_join_requests(modeladmin, request, queryset):
    queryset.update(status="accepted")


@admin.action(description="Reject selected join requests")
def reject_join_requests(modeladmin, request, queryset):
    queryset.update(status="rejected")


@admin.action(description="Cancel selected join requests")
def cancel_join_requests(modeladmin, request, queryset):
    queryset.update(status="cancelled")


@admin.register(ClanJoinRequest)
class ClanJoinRequestAdmin(admin.ModelAdmin):

    list_display = (
        "id",
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
    )

    list_filter = (
        "request_type",
        "status",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = (
        "clan",
        "student",
        "recruitment",
    )

    readonly_fields = ("created_at",)

    actions = (
        accept_join_requests,
        reject_join_requests,
        cancel_join_requests,
    )


# =========================================================
# CLAN LEAVE REQUESTS
# =========================================================


@admin.action(description="Accept selected leave requests")
def accept_leave_requests(modeladmin, request, queryset):
    queryset.update(status="accepted")


@admin.action(description="Reject selected leave requests")
def reject_leave_requests(modeladmin, request, queryset):
    queryset.update(status="rejected")


@admin.action(description="Cancel selected leave requests")
def cancel_leave_requests(modeladmin, request, queryset):
    queryset.update(status="cancelled")


@admin.register(ClanLeaveRequest)
class ClanLeaveRequestAdmin(admin.ModelAdmin):

    list_display = (
        "id",
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

    ordering = ("-created_at",)

    autocomplete_fields = (
        "clan",
        "student",
    )

    readonly_fields = ("created_at",)

    actions = (
        accept_leave_requests,
        reject_leave_requests,
        cancel_leave_requests,
    )


# =========================================================
# CLAN POSTS
# =========================================================


class ClanPostImageInline(admin.TabularInline):
    model = ClanPostImage
    extra = 0


class ClanPostLikeInline(admin.TabularInline):
    model = ClanPostLike
    extra = 0
    autocomplete_fields = ("student",)
    readonly_fields = ("created_at",)


@admin.register(ClanPost)
class ClanPostAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "clan",
        "author",
        "content_preview",
        "has_images",
        "has_video",
        "like_count",
        "created_at",
    )

    search_fields = (
        "content",
        "text",
        "clan__name",
        "author__name",
        "author__user__username",
    )

    list_filter = (
        "clan",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = (
        "clan",
        "author",
    )

    readonly_fields = ("created_at",)

    inlines = (
        ClanPostImageInline,
        ClanPostLikeInline,
    )

    fieldsets = (
        (
            "Post",
            {
                "fields": (
                    "clan",
                    "author",
                    "content",
                    "text",
                )
            },
        ),
        (
            "Media",
            {"fields": ("video",)},
        ),
        (
            "System Information",
            {"fields": ("created_at",)},
        ),
    )

    def content_preview(self, obj):
        text = obj.content or obj.text or ""

        if len(text) > 60:
            return text[:60] + "..."

        return text

    content_preview.short_description = "Content"

    def has_images(self, obj):
        return obj.images.exists()

    has_images.boolean = True
    has_images.short_description = "Images"

    def has_video(self, obj):
        return bool(obj.video)

    has_video.boolean = True
    has_video.short_description = "Video"

    def like_count(self, obj):
        return obj.likes.count()

    like_count.short_description = "Likes"


@admin.register(ClanPostImage)
class ClanPostImageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "post",
        "clan",
        "image",
        "created_at",
    )

    search_fields = (
        "post__content",
        "post__clan__name",
    )

    list_filter = (
        "post__clan",
        "created_at",
    )

    autocomplete_fields = ("post",)

    readonly_fields = ("created_at",)

    def clan(self, obj):
        return obj.post.clan.name

    clan.short_description = "Clan"


@admin.register(ClanPostLike)
class ClanPostLikeAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "post",
        "clan",
        "student",
        "created_at",
    )

    search_fields = (
        "post__content",
        "post__clan__name",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "post__clan",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = (
        "post",
        "student",
    )

    readonly_fields = ("created_at",)

    def clan(self, obj):
        return obj.post.clan.name

    clan.short_description = "Clan"


# =========================================================
# CLAN RECRUITMENT
# =========================================================


class ClanRecruitmentSkillInline(admin.TabularInline):
    model = ClanRecruitmentSkill
    extra = 0
    autocomplete_fields = ("skill",)


@admin.register(ClanRecruitment)
class ClanRecruitmentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "clan",
        "title",
        "created_by",
        "expires_at",
        "is_active_status",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "clan__name",
        "created_by__name",
        "created_by__user__username",
    )

    list_filter = (
        "clan",
        "expires_at",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = (
        "clan",
        "created_by",
    )

    filter_horizontal = ("fields",)

    readonly_fields = (
        "created_at",
        "is_active_status",
    )

    inlines = (ClanRecruitmentSkillInline,)

    def is_active_status(self, obj):
        return obj.is_active

    is_active_status.boolean = True
    is_active_status.short_description = "Active"


@admin.register(ClanRecruitmentSkill)
class ClanRecruitmentSkillAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "recruitment",
        "skill",
        "skill_type",
    )

    search_fields = (
        "recruitment__title",
        "recruitment__clan__name",
        "skill__name",
    )

    list_filter = ("skill__skill_type",)

    autocomplete_fields = (
        "recruitment",
        "skill",
    )

    def skill_type(self, obj):
        return obj.skill.skill_type.name

    skill_type.short_description = "Skill Type"


# =========================================================
# STUDENT RECRUITMENT
# =========================================================


@admin.register(StudentClanRecruitment)
class StudentClanRecruitmentAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "student",
        "message_preview",
        "expires_at",
        "is_active_status",
        "created_at",
    )

    search_fields = (
        "student__name",
        "student__user__username",
        "message",
    )

    list_filter = (
        "expires_at",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = ("student",)

    readonly_fields = (
        "created_at",
        "is_active_status",
    )

    def message_preview(self, obj):
        if len(obj.message) > 70:
            return obj.message[:70] + "..."

        return obj.message

    message_preview.short_description = "Message"

    def is_active_status(self, obj):
        return obj.is_active

    is_active_status.boolean = True
    is_active_status.short_description = "Active"


# =========================================================
# STUDENT PROJECTS
# =========================================================


class StudentProjectLinkInline(admin.TabularInline):
    model = StudentProjectLink
    extra = 0


class StudentProjectImageInline(admin.TabularInline):
    model = StudentProjectImage
    extra = 0


class StudentProjectUpdateInline(admin.TabularInline):
    model = StudentProjectUpdate
    extra = 0


@admin.register(StudentProject)
class StudentProjectAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "student",
        "title",
        "status",
        "started_at",
        "completed_at",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "description",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "status",
        "started_at",
        "completed_at",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = ("student",)

    readonly_fields = (
        "started_at",
        "created_at",
        "updated_at",
    )

    inlines = (
        StudentProjectLinkInline,
        StudentProjectImageInline,
        StudentProjectUpdateInline,
    )


@admin.register(StudentProjectLink)
class StudentProjectLinkAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "student",
        "label",
        "url",
        "created_at",
    )

    search_fields = (
        "label",
        "url",
        "project__title",
        "project__student__name",
    )

    autocomplete_fields = ("project",)

    readonly_fields = ("created_at",)

    def student(self, obj):
        return obj.project.student.name

    student.short_description = "Student"


@admin.register(StudentProjectImage)
class StudentProjectImageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "student",
        "image",
        "is_cover",
        "created_at",
    )

    search_fields = (
        "project__title",
        "project__student__name",
    )

    list_filter = (
        "is_cover",
        "created_at",
    )

    autocomplete_fields = ("project",)

    readonly_fields = ("created_at",)

    def student(self, obj):
        return obj.project.student.name

    student.short_description = "Student"


@admin.register(StudentProjectUpdate)
class StudentProjectUpdateAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "student",
        "caption_preview",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "caption",
        "project__title",
        "project__student__name",
    )

    list_filter = (
        "created_at",
        "updated_at",
    )

    autocomplete_fields = ("project",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    def student(self, obj):
        return obj.project.student.name

    student.short_description = "Student"

    def caption_preview(self, obj):
        if len(obj.caption) > 70:
            return obj.caption[:70] + "..."

        return obj.caption

    caption_preview.short_description = "Caption"


@admin.register(StudentProjectUpdateImage)
class StudentProjectUpdateImageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "update",
        "project",
        "image",
        "created_at",
    )

    search_fields = (
        "update__caption",
        "update__project__title",
        "update__project__student__name",
    )

    autocomplete_fields = ("update",)

    readonly_fields = ("created_at",)

    def project(self, obj):
        return obj.update.project.title

    project.short_description = "Project"


# =========================================================
# OTP REQUEST LOG
# =========================================================


@admin.register(OTPRequestLog)
class OTPRequestLogAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "email",
        "purpose",
        "created_at",
    )

    search_fields = ("email",)

    list_filter = (
        "purpose",
        "created_at",
    )

    ordering = ("-created_at",)

    readonly_fields = ("created_at",)


# =========================================================
# CLAN PROJECTS
# =========================================================


class ClanProjectMemberInline(admin.TabularInline):
    model = ClanProjectMember
    extra = 0
    autocomplete_fields = ("student",)
    readonly_fields = ("joined_project_at",)


class ClanProjectLinkInline(admin.TabularInline):
    model = ClanProjectLink
    extra = 0


class ClanProjectImageInline(admin.TabularInline):
    model = ClanProjectImage
    extra = 0


class ClanProjectUpdateInline(admin.TabularInline):
    model = ClanProjectUpdate
    extra = 0


@admin.register(ClanProject)
class ClanProjectAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "clan",
        "title",
        "status",
        "started_at",
        "completed_at",
        "member_count",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "description",
        "clan__name",
    )

    list_filter = (
        "status",
        "clan",
        "started_at",
        "completed_at",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = ("clan",)

    readonly_fields = (
        "started_at",
        "created_at",
        "updated_at",
    )

    inlines = (
        ClanProjectMemberInline,
        ClanProjectLinkInline,
        ClanProjectImageInline,
        ClanProjectUpdateInline,
    )

    def member_count(self, obj):
        return obj.project_members.count()

    member_count.short_description = "Members"


@admin.register(ClanProjectMember)
class ClanProjectMemberAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "clan",
        "student",
        "joined_project_at",
    )

    search_fields = (
        "project__title",
        "project__clan__name",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "project__clan",
        "joined_project_at",
    )

    autocomplete_fields = (
        "project",
        "student",
    )

    readonly_fields = ("joined_project_at",)

    def clan(self, obj):
        return obj.project.clan.name

    clan.short_description = "Clan"


@admin.register(ClanProjectLink)
class ClanProjectLinkAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "clan",
        "label",
        "url",
        "created_at",
    )

    search_fields = (
        "label",
        "url",
        "project__title",
        "project__clan__name",
    )

    autocomplete_fields = ("project",)

    readonly_fields = ("created_at",)

    def clan(self, obj):
        return obj.project.clan.name

    clan.short_description = "Clan"


@admin.register(ClanProjectImage)
class ClanProjectImageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "clan",
        "image",
        "is_cover",
        "created_at",
    )

    search_fields = (
        "project__title",
        "project__clan__name",
    )

    list_filter = (
        "is_cover",
        "created_at",
    )

    autocomplete_fields = ("project",)

    readonly_fields = ("created_at",)

    def clan(self, obj):
        return obj.project.clan.name

    clan.short_description = "Clan"


@admin.register(ClanProjectUpdate)
class ClanProjectUpdateAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "project",
        "clan",
        "caption_preview",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "caption",
        "project__title",
        "project__clan__name",
    )

    list_filter = (
        "created_at",
        "updated_at",
    )

    autocomplete_fields = ("project",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    def clan(self, obj):
        return obj.project.clan.name

    clan.short_description = "Clan"

    def caption_preview(self, obj):
        if len(obj.caption) > 70:
            return obj.caption[:70] + "..."

        return obj.caption

    caption_preview.short_description = "Caption"


@admin.register(ClanProjectUpdateImage)
class ClanProjectUpdateImageAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "update",
        "project",
        "image",
        "created_at",
    )

    search_fields = (
        "update__caption",
        "update__project__title",
        "update__project__clan__name",
    )

    autocomplete_fields = ("update",)

    readonly_fields = ("created_at",)

    def project(self, obj):
        return obj.update.project.title

    project.short_description = "Project"


@admin.register(ClanProjectUpdateParticipant)
class ClanProjectUpdateParticipantAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "update",
        "project",
        "student",
        "created_at",
    )

    search_fields = (
        "update__caption",
        "update__project__title",
        "project_member__student__name",
        "project_member__student__user__username",
    )

    list_filter = ("created_at",)

    autocomplete_fields = (
        "update",
        "project_member",
    )

    readonly_fields = ("created_at",)

    def project(self, obj):
        return obj.update.project.title

    project.short_description = "Project"

    def student(self, obj):
        return obj.project_member.student.name

    student.short_description = "Student"


# =========================================================
# CLAN STORIES
# =========================================================


class ClanStoryViewInline(admin.TabularInline):
    model = ClanStoryView
    extra = 0
    autocomplete_fields = ("student",)
    readonly_fields = ("viewed_at",)


class ClanStoryLikeInline(admin.TabularInline):
    model = ClanStoryLike
    extra = 0
    autocomplete_fields = ("student",)
    readonly_fields = ("created_at",)


@admin.register(ClanStory)
class ClanStoryAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "clan",
        "story_type",
        "created_at",
        "expires_at",
        "is_active_status",
        "view_count",
        "like_count",
    )

    search_fields = (
        "clan__name",
        "text",
        "caption",
    )

    list_filter = (
        "story_type",
        "clan",
        "created_at",
        "expires_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = ("clan",)

    readonly_fields = (
        "created_at",
        "is_active_status",
        "view_count",
        "like_count",
    )

    inlines = (
        ClanStoryViewInline,
        ClanStoryLikeInline,
    )

    fieldsets = (
        (
            "Story",
            {
                "fields": (
                    "clan",
                    "story_type",
                    "text",
                    "caption",
                )
            },
        ),
        (
            "Media",
            {
                "fields": (
                    "image",
                    "video",
                )
            },
        ),
        (
            "Expiry",
            {
                "fields": (
                    "expires_at",
                    "is_active_status",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "view_count",
                    "like_count",
                )
            },
        ),
        (
            "System Information",
            {"fields": ("created_at",)},
        ),
    )

    def is_active_status(self, obj):
        return obj.is_active

    is_active_status.boolean = True
    is_active_status.short_description = "Active"

    def view_count(self, obj):
        return obj.views.count()

    view_count.short_description = "Views"

    def like_count(self, obj):
        return obj.likes.count()

    like_count.short_description = "Likes"


@admin.register(ClanStoryView)
class ClanStoryViewAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "story",
        "clan",
        "student",
        "viewed_at",
    )

    search_fields = (
        "story__clan__name",
        "story__text",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "story__clan",
        "viewed_at",
    )

    ordering = ("-viewed_at",)

    autocomplete_fields = (
        "story",
        "student",
    )

    readonly_fields = ("viewed_at",)

    def clan(self, obj):
        return obj.story.clan.name

    clan.short_description = "Clan"


@admin.register(ClanStoryLike)
class ClanStoryLikeAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "story",
        "clan",
        "student",
        "created_at",
    )

    search_fields = (
        "story__clan__name",
        "story__text",
        "student__name",
        "student__user__username",
    )

    list_filter = (
        "story__clan",
        "created_at",
    )

    ordering = ("-created_at",)

    autocomplete_fields = (
        "story",
        "student",
    )

    readonly_fields = ("created_at",)

    def clan(self, obj):
        return obj.story.clan.name

    clan.short_description = "Clan"

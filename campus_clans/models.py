from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User


# ============================================================
# STUDENT PROFILE
# ============================================================

class StudentProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    name = models.CharField(
        max_length=150
    )

    department = models.CharField(
        max_length=100
    )

    branch = models.CharField(
        max_length=150
    )

    email = models.EmailField(
        unique=True
    )

    email_verified = models.BooleanField(
        default=False
    )

    about = models.TextField(
        blank=True
    )

    github = models.URLField(
        blank=True
    )

    linkedin = models.URLField(
        blank=True
    )

    instagram = models.URLField(
        blank=True
    )

    youtube = models.URLField(
        blank=True
    )

    profile_picture = models.ImageField(
        upload_to="profile_pictures/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.user.username


# ============================================================
# SKILL TYPE
# ============================================================

class SkillType(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    def __str__(self):
        return self.name


# ============================================================
# SKILL
# ============================================================

class Skill(models.Model):

    skill_type = models.ForeignKey(
        SkillType,
        on_delete=models.CASCADE,
        related_name="skills"
    )

    name = models.CharField(
        max_length=100
    )

    class Meta:
        unique_together = (
            "skill_type",
            "name",
        )

    def __str__(self):
        return self.name


# ============================================================
# STUDENT SELECTED SKILL
# ============================================================

class StudentSkill(models.Model):

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="student_skills"
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="student_skills"
    )

    is_highlighted = models.BooleanField(
        default=False
    )

    class Meta:
        unique_together = (
            "student",
            "skill",
        )

    def __str__(self):
        return (
            f"{self.student.user.username} - "
            f"{self.skill.name}"
        )


class Clan(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    logo = models.ImageField(
        upload_to="clan_logos/",
        blank=True,
        null=True
    )

    banner = models.ImageField(
        upload_to="clan_banners/",
        blank=True,
        null=True
    )

    speciality = models.CharField(
        max_length=150
    )

    profile_description = models.CharField(
        max_length=50
    )

    description = models.TextField()

    created_by = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="created_clan"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.name

class StudentClanRecruitment(models.Model):

    student = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_recruitment_request"
    )

    message = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    expires_at = models.DateTimeField()

    def __str__(self):
        return (
            f"{self.student.name} - "
            f"Looking for Clan"
        )

    @property
    def is_active(self):
        return timezone.now() < self.expires_at

class ClanMember(models.Model):

    ROLE_CHOICES = [
        ("member", "Member"),
        ("co_leader", "Co-Leader"),
        ("leader", "Leader"),
    ]

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="members"
    )

    student = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_membership"
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="member"
    )

    joined_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [

            # Only ONE leader per clan
            models.UniqueConstraint(
                fields=["clan"],
                condition=models.Q(role="leader"),
                name="one_leader_per_clan"
            ),

            # Only ONE co-leader per clan
            models.UniqueConstraint(
                fields=["clan"],
                condition=models.Q(role="co_leader"),
                name="one_co_leader_per_clan"
            ),
        ]

    def __str__(self):
        return (
            f"{self.student.name} - "
            f"{self.clan.name} "
            f"({self.get_role_display()})"
        )


class ClanInvitation(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="invitations"
    )

    invited_student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_invitations"
    )

    invited_by = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="sent_clan_invitations"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    responded_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "clan",
                    "invited_student",
                ],
                condition=models.Q(status="pending"),
                name="unique_pending_clan_invitation"
            )
        ]

    def __str__(self):
        return (
            f"{self.clan.name} → "
            f"{self.invited_student.name} "
            f"({self.status})"
        )

class ClanJoinRequest(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    REQUEST_TYPE_CHOICES = [
        ("direct", "Direct"),
        ("global", "Global Recruitment"),
    ]

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="join_requests"
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_join_requests"
    )

    request_type = models.CharField(
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default="direct"
    )

    recruitment = models.ForeignKey(
        "ClanRecruitment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="join_requests"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    responded_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "clan",
                    "student",
                ],
                condition=models.Q(status="pending"),
                name="unique_pending_clan_join_request"
            )
        ]

    def __str__(self):
        return (
            f"{self.student.name} → "
            f"{self.clan.name} "
            f"({self.status})"
        )


class ClanLeaveRequest(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="leave_requests"
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_leave_requests"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    responded_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "clan",
                    "student",
                ],
                condition=models.Q(status="pending"),
                name="unique_pending_clan_leave_request"
            )
        ]

    def __str__(self):
        return (
            f"{self.student.name} → "
            f"Leave {self.clan.name} "
            f"({self.status})"
        )


class ClanPost(models.Model):

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="posts"
    )

    author = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_posts"
    )

    content = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="clan_posts/",
        blank=True,
        null=True
    )

    caption = models.CharField(
        max_length=500,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.clan.name} - "
            f"Post"
        )

class ClanPostLike(models.Model):

    post = models.ForeignKey(
        ClanPost,
        on_delete=models.CASCADE,
        related_name="likes"
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_post_likes"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "post",
                    "student",
                ],
                name="unique_clan_post_like"
            )
        ]

    def __str__(self):
        return (
            f"{self.student.name} liked "
            f"{self.post.clan.name} post"
        )


class ClanStory(models.Model):

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="stories"
    )

    author = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_stories"
    )

    content = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="clan_stories/",
        blank=True,
        null=True
    )

    caption = models.CharField(
        max_length=500,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f"{self.clan.name} - "
            f"Story"
        )

    @property
    def is_expired(self):

        from datetime import timedelta

        return timezone.now() >= (
            self.created_at + timedelta(hours=24)
        )

class ClanStoryView(models.Model):

    story = models.ForeignKey(
        ClanStory,
        on_delete=models.CASCADE,
        related_name="views"
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="viewed_clan_stories"
    )

    viewed_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "story",
                    "student",
                ],
                name="unique_story_viewer"
            )
        ]

    def __str__(self):
        return (
            f"{self.student.name} viewed "
            f"{self.story.clan.name} story"
        )

class ClanRecruitment(models.Model):

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        related_name="recruitments"
    )

    created_by = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="created_clan_recruitments"
    )

    title = models.CharField(
        max_length=150
    )

    description = models.TextField(
        blank=True
    )

    # Multiple fields can be selected
    fields = models.ManyToManyField(
        SkillType,
        related_name="clan_recruitments",
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    expires_at = models.DateTimeField()

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f"{self.clan.name} - "
            f"{self.title}"
        )

    @property
    def is_active(self):
        return timezone.now() < self.expires_at

class ClanRecruitmentSkill(models.Model):

    recruitment = models.ForeignKey(
        ClanRecruitment,
        on_delete=models.CASCADE,
        related_name="required_skills"
    )

    skill = models.ForeignKey(
        Skill,
        on_delete=models.CASCADE,
        related_name="clan_recruitment_skills"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "recruitment",
                    "skill",
                ],
                name="unique_recruitment_skill"
            )
        ]

    def __str__(self):
        return (
            f"{self.recruitment.title} - "
            f"{self.skill.name}"
        )
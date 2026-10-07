from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q


class StudentProfile(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    name = models.CharField(max_length=150)

    department = models.CharField(max_length=100)

    branch = models.CharField(max_length=150)

    email = models.EmailField(unique=True)

    email_verified = models.BooleanField(default=False)

    about = models.TextField(blank=True)

    github = models.URLField(blank=True)

    linkedin = models.URLField(blank=True)

    instagram = models.URLField(blank=True)

    youtube = models.URLField(blank=True)

    profile_picture = models.ImageField(
        upload_to="profile_pictures/", blank=True, null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SkillType(models.Model):

    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Skill(models.Model):

    skill_type = models.ForeignKey(
        SkillType, on_delete=models.CASCADE, related_name="skills"
    )

    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class StudentSkill(models.Model):

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="student_skills"
    )

    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="student_skills"
    )

    is_highlighted = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "skill"], name="unique_student_skill"
            )
        ]

    def __str__(self):
        return f"{self.student.name} - {self.skill.name}"


class Clan(models.Model):

    name = models.CharField(max_length=100, unique=True)

    logo = models.ImageField(upload_to="clan_logos/", blank=True, null=True)

    banner = models.ImageField(upload_to="clan_banners/", blank=True, null=True)

    speciality = models.CharField(max_length=150)

    profile_description = models.CharField(max_length=50)

    description = models.TextField()

    created_by = models.OneToOneField(
        StudentProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_clan",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ClanMember(models.Model):

    ROLE_CHOICES = [
        ("member", "Member"),
        ("co_leader", "Co-Leader"),
        ("leader", "Leader"),
    ]

    clan = models.ForeignKey(Clan, on_delete=models.CASCADE, related_name="members")

    student = models.OneToOneField(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_membership"
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clan"], condition=Q(role="leader"), name="one_leader_per_clan"
            ),
            models.UniqueConstraint(
                fields=["clan"],
                condition=Q(role="co_leader"),
                name="one_co_leader_per_clan",
            ),
        ]

    def __str__(self):
        return f"{self.student.name} - {self.clan.name}"


class ClanInvitation(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    clan = models.ForeignKey(Clan, on_delete=models.CASCADE, related_name="invitations")

    invited_student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_invitations"
    )

    invited_by = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="sent_clan_invitations"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)

    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clan", "invited_student"],
                condition=Q(status="pending"),
                name="unique_pending_clan_invitation",
            )
        ]

    def __str__(self):
        return f"{self.clan.name} -> {self.invited_student.name}"


class ClanJoinRequest(models.Model):

    REQUEST_TYPE_CHOICES = [
        ("direct", "Direct"),
        ("global", "Global"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    clan = models.ForeignKey(
        Clan, on_delete=models.CASCADE, related_name="join_requests"
    )

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_join_requests"
    )

    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES)

    recruitment = models.ForeignKey(
        "ClanRecruitment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="join_requests",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)

    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clan", "student"],
                condition=Q(status="pending"),
                name="unique_pending_clan_join_request",
            )
        ]

    def __str__(self):
        return f"{self.student.name} -> {self.clan.name}"


class ClanLeaveRequest(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    clan = models.ForeignKey(
        Clan, on_delete=models.CASCADE, related_name="leave_requests"
    )

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_leave_requests"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)

    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["clan", "student"],
                condition=Q(status="pending"),
                name="unique_pending_clan_leave_request",
            )
        ]

    def __str__(self):
        return f"{self.student.name} - {self.clan.name}"


class ClanPost(models.Model):
    clan = models.ForeignKey(Clan, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_posts"
    )
    content = models.TextField(blank=True)
    text = models.TextField(blank=True)
    video = models.FileField(upload_to="clan_posts/videos/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ClanPostImage(models.Model):

    post = models.ForeignKey(ClanPost, on_delete=models.CASCADE, related_name="images")

    image = models.ImageField(upload_to="clan_posts/images/")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.post.clan.name} - Post {self.post.id} - Image {self.id}"


class ClanPostLike(models.Model):

    post = models.ForeignKey(ClanPost, on_delete=models.CASCADE, related_name="likes")

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="liked_posts"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["post", "student"], name="unique_post_like")
        ]

    def __str__(self):
        return f"{self.student.name} - {self.post.id}"


class ClanRecruitment(models.Model):

    clan = models.ForeignKey(
        Clan, on_delete=models.CASCADE, related_name="recruitments"
    )

    created_by = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="created_recruitments"
    )

    title = models.CharField(max_length=200)

    description = models.TextField()

    fields = models.ManyToManyField(SkillType, blank=True, related_name="recruitments")

    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_active(self):
        from django.utils import timezone

        return timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.clan.name} - {self.title}"


class ClanRecruitmentSkill(models.Model):

    recruitment = models.ForeignKey(
        ClanRecruitment, on_delete=models.CASCADE, related_name="recruitment_skills"
    )

    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="recruitment_skills"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["recruitment", "skill"], name="unique_recruitment_skill"
            )
        ]

    def __str__(self):
        return f"{self.recruitment.title} - {self.skill.name}"


class StudentClanRecruitment(models.Model):

    student = models.OneToOneField(
        StudentProfile, on_delete=models.CASCADE, related_name="student_recruitment"
    )

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField()

    @property
    def is_active(self):
        from django.utils import timezone

        return timezone.now() < self.expires_at

    def __str__(self):
        return f"{self.student.name} - Recruitment"


# =========================================================
# STUDENT PROJECTS
# =========================================================


class StudentProject(models.Model):

    STATUS_CHOICES = [
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
    ]

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="personal_projects"
    )

    title = models.CharField(max_length=200)

    description = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ongoing")

    cover_image = models.ImageField(
        upload_to="student_project_covers/", null=True, blank=True
    )

    started_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.name} - {self.title}"


class StudentProjectLink(models.Model):

    project = models.ForeignKey(
        StudentProject, on_delete=models.CASCADE, related_name="links"
    )

    label = models.CharField(max_length=100)

    url = models.URLField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.title} - {self.label}"


class StudentProjectImage(models.Model):

    project = models.ForeignKey(
        StudentProject, on_delete=models.CASCADE, related_name="images"
    )

    image = models.ImageField(upload_to="student_projects/")

    is_cover = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.title} - Image {self.id}"


class StudentProjectUpdate(models.Model):

    project = models.ForeignKey(
        StudentProject, on_delete=models.CASCADE, related_name="updates"
    )

    caption = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.title} - Update {self.id}"


class StudentProjectUpdateImage(models.Model):

    update = models.ForeignKey(
        StudentProjectUpdate, on_delete=models.CASCADE, related_name="images"
    )

    image = models.ImageField(upload_to="student_project_updates/")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image - {self.update.project.title} - Update {self.update.id}"


class OTPRequestLog(models.Model):

    PURPOSE_CHOICES = [
        ("registration", "Registration"),
        ("password_reset", "Password Reset"),
    ]

    email = models.EmailField()

    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["email", "purpose", "created_at"])]

    def __str__(self):
        return f"{self.email} - {self.purpose} - {self.created_at}"


# =========================================================
# CLAN PROJECTS
# =========================================================


class ClanProject(models.Model):

    STATUS_CHOICES = [
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
    ]

    clan = models.ForeignKey(Clan, on_delete=models.CASCADE, related_name="projects")

    title = models.CharField(max_length=200)

    description = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ongoing")

    cover_image = models.ImageField(
        upload_to="clan_project_covers/", null=True, blank=True
    )

    started_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.clan.name} - {self.title}"


class ClanProjectMember(models.Model):

    project = models.ForeignKey(
        ClanProject, on_delete=models.CASCADE, related_name="project_members"
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="clan_project_memberships",
    )

    joined_project_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "student"], name="unique_clan_project_member"
            )
        ]

    def __str__(self):
        return f"{self.student.name} - {self.project.title}"


class ClanProjectLink(models.Model):

    project = models.ForeignKey(
        ClanProject, on_delete=models.CASCADE, related_name="links"
    )

    label = models.CharField(max_length=100)

    url = models.URLField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.title} - {self.label}"


class ClanProjectImage(models.Model):

    project = models.ForeignKey(
        ClanProject, on_delete=models.CASCADE, related_name="images"
    )

    image = models.ImageField(upload_to="clan_projects/")

    is_cover = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.project.title} - Image {self.id}"


class ClanProjectUpdate(models.Model):

    project = models.ForeignKey(
        ClanProject, on_delete=models.CASCADE, related_name="updates"
    )

    caption = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.project.title} - Update {self.id}"


class ClanProjectUpdateImage(models.Model):

    update = models.ForeignKey(
        ClanProjectUpdate, on_delete=models.CASCADE, related_name="images"
    )

    image = models.ImageField(upload_to="clan_project_updates/")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image - {self.update.project.title} " f"- Update {self.update.id}"


class ClanProjectUpdateParticipant(models.Model):

    update = models.ForeignKey(
        ClanProjectUpdate, on_delete=models.CASCADE, related_name="participants"
    )

    project_member = models.ForeignKey(
        ClanProjectMember,
        on_delete=models.CASCADE,
        related_name="update_participations",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["update", "project_member"],
                name="unique_update_project_participant",
            )
        ]

    def __str__(self):
        return f"{self.project_member.student.name} " f"- Update {self.update.id}"


# =========================================================
# CLAN STORIES
# =========================================================


class ClanStory(models.Model):

    STORY_TYPES = [
        ("text", "Text"),
        ("image", "Image"),
        ("video", "Video"),
    ]

    clan = models.ForeignKey(Clan, on_delete=models.CASCADE, related_name="stories")

    story_type = models.CharField(max_length=10, choices=STORY_TYPES)

    text = models.TextField(blank=True, null=True)

    caption = models.TextField(blank=True, null=True)

    image = models.ImageField(upload_to="clan_stories/images/", blank=True, null=True)

    video = models.FileField(upload_to="clan_stories/videos/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.clan.name} - {self.story_type}"


class ClanStoryView(models.Model):

    story = models.ForeignKey(ClanStory, on_delete=models.CASCADE, related_name="views")

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_story_views"
    )

    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "student"], name="unique_clan_story_view"
            )
        ]

    def __str__(self):
        return f"{self.student.name} viewed story {self.story.id}"


class ClanStoryLike(models.Model):

    story = models.ForeignKey(ClanStory, on_delete=models.CASCADE, related_name="likes")

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="clan_story_likes"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["story", "student"], name="unique_clan_story_like"
            )
        ]

    def __str__(self):
        return f"{self.student.name} liked story {self.story.id}"


# ============================================================
# CAMPUS EVENTS
# ============================================================


class Event(models.Model):

    name = models.CharField(max_length=200)

    description = models.TextField()

    start_date = models.DateTimeField()

    end_date = models.DateTimeField()

    link = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def is_ended(self):
        from django.utils import timezone

        return timezone.now() >= self.end_date

    @property
    def trophy_deadline(self):
        from datetime import timedelta

        return self.end_date + timedelta(days=2)

    @property
    def trophy_window_open(self):
        from django.utils import timezone

        now = timezone.now()

        return self.is_ended and now <= self.trophy_deadline


class EventMedia(models.Model):

    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="media")

    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)

    image = models.ImageField(upload_to="events/images/", blank=True, null=True)

    video = models.FileField(upload_to="events/videos/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event.name} - {self.media_type}"

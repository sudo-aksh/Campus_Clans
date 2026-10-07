from django.db import models
from campus_clans.models import StudentProfile, Clan, Q


class ClanMembershipHistory(models.Model):
    clan = models.ForeignKey(Clan, on_delete=models.SET_NULL, null=True, blank=True)
    clan_name = models.CharField(max_length=100)
    student = models.ForeignKey(
        StudentProfile, on_delete=models.SET_NULL, null=True, blank=True
    )
    student_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20)
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student_name} - {self.clan_name}"


class Event(models.Model):

    PARTICIPANT_TYPE_CHOICES = [
        ("clan", "Clan"),
        ("student", "Student"),
        ("both", "Both"),
    ]
    name = models.CharField(max_length=200)
    description = models.TextField()
    participant_type = models.CharField(
        max_length=10,
        choices=PARTICIPANT_TYPE_CHOICES,
        default="clan",
    )
    link = models.URLField(blank=True)
    image = models.ImageField(upload_to="campus_events/", blank=True, null=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def trophy_deadline(self):
        from datetime import timedelta

        return self.end_date + timedelta(days=2)

    @property
    def trophy_window_open(self):
        from django.utils import timezone

        return (
            timezone.now() >= self.end_date and timezone.now() <= self.trophy_deadline
        )


class EventMedia(models.Model):
    MEDIA_TYPES = (("image", "Image"), ("video", "Video"))
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(upload_to="campus_events/media/")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event.name} - {self.media_type}"


class ClanEventApplication(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="applications"
    )
    clan = models.ForeignKey(
        Clan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_applications",
    )
    clan_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    applied_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    participated = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.clan_name} - {self.event.name}"


class EventParticipation(models.Model):

    PARTICIPANT_TYPE_CHOICES = [
        ("clan", "Clan"),
        ("student", "Student"),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="participations"
    )

    participant_type = models.CharField(
        max_length=10,
        choices=PARTICIPANT_TYPE_CHOICES,
        default="clan",
    )

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="event_participations",
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="event_participations",
    )

    participated_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-participated_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["event", "clan"],
                condition=Q(clan__isnull=False),
                name="unique_event_clan_participation",
            ),
            models.UniqueConstraint(
                fields=["event", "student"],
                condition=Q(student__isnull=False),
                name="unique_event_student_participation",
            ),
        ]


class EventTrophy(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="trophies"
    )

    clan = models.ForeignKey(
        Clan,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="event_trophies"
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="event_trophies"
    )

    award_name = models.CharField(max_length=100)

    description = models.TextField(blank=True)

    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "clan", "award_name"],
                name="unique_event_clan_award",
            ),
            models.UniqueConstraint(
                fields=["event", "student", "award_name"],
                name="unique_event_student_award",
            ),
        ]

    def __str__(self):
        recipient = self.clan.name if self.clan else self.student.name
        return f"{self.award_name} - {recipient}"


class DeletedStudentRecord(models.Model):
    name = models.CharField(max_length=150)
    username = models.CharField(max_length=150)
    email = models.EmailField()
    department = models.CharField(max_length=100)
    branch = models.CharField(max_length=150)
    original_created_at = models.DateTimeField()
    deleted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.username})"


class DeletedClanRecord(models.Model):
    name = models.CharField(max_length=100)
    speciality = models.CharField(max_length=150)
    description = models.TextField()
    created_by_name = models.CharField(max_length=150, blank=True)
    original_created_at = models.DateTimeField()
    deleted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class StudentSuspension(models.Model):
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspensions",
    )
    student_name = models.CharField(max_length=150)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.student_name} until {self.end_date}"


class ClanSuspension(models.Model):
    clan = models.ForeignKey(
        Clan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suspensions",
    )
    clan_name = models.CharField(max_length=100)
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.clan_name} until {self.end_date}"


class AdminAction(models.Model):
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.IntegerField(null=True, blank=True)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.target_type}"


class AdminMessage(models.Model):
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="admin_messages"
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject} - {self.student.name}"


class ClanAdminMessage(models.Model):
    clan = models.ForeignKey(
        Clan, on_delete=models.CASCADE, related_name="admin_messages"
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject} - {self.clan.name}"


class ClanMessage(models.Model):
    clan = models.ForeignKey(Clan, on_delete=models.CASCADE, related_name="messages")
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_admin_message = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.clan.name} - {self.subject}"

class EventClanParticipant(models.Model):
    participation = models.ForeignKey(
        EventParticipation,
        on_delete=models.CASCADE,
        related_name="selected_members",
    )

    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="event_clan_participations",
    )

    selected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["selected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["participation", "student"],
                name="unique_event_clan_selected_member",
            )
        ]

    def __str__(self):
        return (
            f"{self.student.name} - "
            f"{self.participation.clan.name} - "
            f"{self.participation.event.name}"
        )
from django.contrib import admin
from .models import (
    AdminAction, AdminMessage, ClanAdminMessage, ClanEventApplication,
    ClanMembershipHistory, ClanMessage, ClanSuspension, DeletedClanRecord,
    DeletedStudentRecord, Event, EventMedia, EventParticipation, EventTrophy,
    StudentSuspension,
)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "created_at")
    search_fields = ("name", "description")
    ordering = ("-end_date",)
    inlines = []


@admin.register(EventMedia)
class EventMediaAdmin(admin.ModelAdmin):
    list_display = ("event", "media_type", "created_at")
    list_filter = ("media_type",)
    search_fields = ("event__name",)


@admin.register(EventParticipation)
class EventParticipationAdmin(admin.ModelAdmin):
    list_display = ("event", "clan", "participated_at")
    search_fields = ("event__name", "clan__name")
    ordering = ("-participated_at",)


@admin.register(EventTrophy)
class EventTrophyAdmin(admin.ModelAdmin):
    list_display = ("event", "clan", "award_name", "awarded_at")
    search_fields = ("event__name", "clan__name", "award_name")
    ordering = ("-awarded_at",)


@admin.register(ClanEventApplication)
class ClanEventApplicationAdmin(admin.ModelAdmin):
    list_display = ("event", "clan_name", "status", "participated", "applied_at")
    list_filter = ("status", "participated")
    search_fields = ("event__name", "clan_name")


@admin.register(ClanMembershipHistory)
class ClanMembershipHistoryAdmin(admin.ModelAdmin):
    list_display = ("clan_name", "student_name", "role", "joined_at", "left_at")
    search_fields = ("clan_name", "student_name")


@admin.register(DeletedStudentRecord)
class DeletedStudentRecordAdmin(admin.ModelAdmin):
    list_display = ("name", "username", "email", "department", "branch", "deleted_at")
    search_fields = ("name", "username", "email")


@admin.register(DeletedClanRecord)
class DeletedClanRecordAdmin(admin.ModelAdmin):
    list_display = ("name", "speciality", "created_by_name", "deleted_at")
    search_fields = ("name", "created_by_name")


@admin.register(StudentSuspension)
class StudentSuspensionAdmin(admin.ModelAdmin):
    list_display = ("student_name", "start_date", "end_date", "is_active", "reason")
    list_filter = ("is_active",)
    search_fields = ("student_name",)


@admin.register(ClanSuspension)
class ClanSuspensionAdmin(admin.ModelAdmin):
    list_display = ("clan_name", "start_date", "end_date", "is_active", "reason")
    list_filter = ("is_active",)
    search_fields = ("clan_name",)


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("description",)
    ordering = ("-created_at",)


@admin.register(AdminMessage)
class AdminMessageAdmin(admin.ModelAdmin):
    list_display = ("student", "subject", "is_read", "created_at")
    list_filter = ("is_read",)
    search_fields = ("student__name", "student__user__username", "subject", "message")
    ordering = ("-created_at",)


@admin.register(ClanAdminMessage)
class ClanAdminMessageAdmin(admin.ModelAdmin):
    list_display = ("clan", "subject", "created_at")
    search_fields = ("clan__name", "subject", "message")
    ordering = ("-created_at",)


@admin.register(ClanMessage)
class ClanMessageAdmin(admin.ModelAdmin):
    list_display = ("clan", "subject", "is_admin_message", "created_at")
    list_filter = ("is_admin_message",)
    search_fields = ("clan__name", "subject", "message")
    ordering = ("-created_at",)

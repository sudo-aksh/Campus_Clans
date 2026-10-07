from django.urls import path
from . import views

urlpatterns = [
    # =========================
    # AUTH
    # =========================
    path("", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path(
        "send-password-reset-otp/",
        views.send_password_reset_otp,
        name="send_password_reset_otp",
    ),
    path(
        "verify-password-reset-otp/",
        views.verify_password_reset_otp,
        name="verify_password_reset_otp",
    ),
    path("reset-password/", views.reset_password, name="reset_password"),
    path("send-otp/", views.send_otp, name="send_otp"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("register-student/", views.register_student, name="register_student"),
    path("logout/", views.logout_view, name="logout"),
    # =========================
    # DASHBOARDS
    # =========================
    path("student-dashboard/", views.student_dashboard, name="student_dashboard"),
    path("home/", views.home, name="home"),
    # =========================
    # PROFILE
    # =========================
    path("profile/", views.profile_view, name="profile"),
    path("profile/<int:student_id>/", views.view_profile, name="view_profile"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path(
        "send-email-change-otp/",
        views.send_email_change_otp,
        name="send_email_change_otp",
    ),
    path(
        "verify-email-change-otp/",
        views.verify_email_change_otp,
        name="verify_email_change_otp",
    ),
    # =========================
    # SKILLS
    # =========================
    path("skills/<int:skill_type_id>/", views.get_skills, name="get_skills"),
    # =========================
    # CLAN CREATION
    # =========================
    path("create-clan/", views.create_clan, name="create_clan"),
    # =========================
    # CLAN PROFILE
    # =========================
    path("clan/<int:clan_id>/", views.clan_profile, name="clan_profile"),
    path("clan/<int:clan_id>/edit/", views.edit_clan, name="edit_clan"),
    path("clan/<int:clan_id>/delete/", views.delete_clan, name="delete_clan"),
    path(
        "clan/<int:clan_id>/remove-member/<int:member_id>/",
        views.remove_clan_member,
        name="remove_clan_member",
    ),
    path(
        "clan/<int:clan_id>/change-role/<int:member_id>/",
        views.change_clan_member_role,
        name="change_clan_member_role",
    ),
    # =========================
    # STUDENT SEARCH
    # =========================
    path("student-search/", views.student_search, name="student_search"),
    path("search/", views.search, name="search"),
    path("search/suggestions/", views.search_suggestions, name="search_suggestions"),
    # =========================
    # CLAN INVITATIONS
    # =========================
    path(
        "clan/<int:student_id>/invite/",
        views.send_clan_invitation,
        name="send_clan_invitation",
    ),
    path(
        "clan-invitation/<int:invitation_id>/accept/",
        views.accept_clan_invitation,
        name="accept_clan_invitation",
    ),
    path(
        "clan-invitation/<int:invitation_id>/reject/",
        views.reject_clan_invitation,
        name="reject_clan_invitation",
    ),
    path(
        "clan-invitation/<int:invitation_id>/cancel/",
        views.cancel_clan_invitation,
        name="cancel_clan_invitation",
    ),
    # =========================
    # CLAN JOIN REQUESTS
    # =========================
    path(
        "clan/<int:clan_id>/join/",
        views.send_clan_join_request,
        name="send_clan_join_request",
    ),
    path(
        "clan-join-request/<int:request_id>/cancel/",
        views.cancel_clan_join_request,
        name="cancel_clan_join_request",
    ),
    path(
        "clan-join-request/<int:request_id>/accept/",
        views.accept_clan_join_request,
        name="accept_clan_join_request",
    ),
    path(
        "clan-join-request/<int:request_id>/reject/",
        views.reject_clan_join_request,
        name="reject_clan_join_request",
    ),
    # =========================
    # CLAN STORIES
    # =========================
    # Opens the story creation page
    path(
        "clan/<int:clan_id>/story/create/",
        views.create_clan_story_page,
        name="create_clan_story_page",
    ),
    # Processes the story form
    path(
        "clan/<int:clan_id>/story/create/save/",
        views.create_clan_story,
        name="create_clan_story",
    ),
    # View a story
    path("clan-story/<int:story_id>/", views.view_clan_story, name="view_clan_story"),
    # Story viewers
    path(
        "clan-story/<int:story_id>/viewers/",
        views.clan_story_viewers,
        name="clan_story_viewers",
    ),
    path(
        "clan-story/<int:story_id>/delete/",
        views.delete_clan_story,
        name="delete_clan_story",
    ),
    path(
        "story/<int:story_id>/view/",
        views.record_clan_story_view,
        name="record_clan_story_view",
    ),
    path(
        "story/<int:story_id>/like/",
        views.like_clan_story,
        name="like_clan_story",
    ),
    # =========================
    # CLAN POSTS
    # =========================
    path(
        "clan/<int:clan_id>/post/create/",
        views.create_clan_post_page,
        name="create_clan_post_page",
    ),
    path(
        "clan/<int:clan_id>/post/create/submit/",
        views.create_clan_post,
        name="create_clan_post",
    ),
    path("clan-post/<int:post_id>/edit/", views.edit_clan_post, name="edit_clan_post"),
    path(
        "clan/post/<int:post_id>/like/",
        views.toggle_clan_post_like,
        name="toggle_clan_post_like",
    ),
    path(
        "clan-post/<int:post_id>/likes/", views.clan_post_likes, name="clan_post_likes"
    ),
    path(
        "clan-post/<int:post_id>/delete",
        views.delete_clan_post,
        name="delete_clan_post",
    ),
    path(
        "clan/<int:clan_id>/recruitment/create/",
        views.create_clan_recruitment,
        name="create_clan_recruitment",
    ),
    path("global-recruitments/", views.global_recruitments, name="global_recruitments"),
    path(
        "global-recruitments/<int:recruitment_id>/request/",
        views.send_global_clan_join_request,
        name="send_global_clan_join_request",
    ),
    path(
        "clan/<int:clan_id>/leave-request/",
        views.request_clan_leave,
        name="request_clan_leave",
    ),
    path(
        "clan/leave-request/<int:request_id>/accept/",
        views.accept_clan_leave_request,
        name="accept_clan_leave_request",
    ),
    path(
        "clan/leave-request/<int:request_id>/reject/",
        views.reject_clan_leave_request,
        name="reject_clan_leave_request",
    ),
    path(
        "clan/recruitment/<int:recruitment_id>/edit/",
        views.edit_clan_recruitment,
        name="edit_clan_recruitment",
    ),
    path(
        "clan/recruitment/<int:recruitment_id>/delete/",
        views.delete_clan_recruitment,
        name="delete_clan_recruitment",
    ),
    path(
        "student-recruitments/",
        views.student_clan_recruitments,
        name="student_clan_recruitments",
    ),
    path(
        "student-recruitment/create/",
        views.create_student_clan_recruitment,
        name="create_student_clan_recruitment",
    ),
    path(
        "student-recruitment/<int:recruitment_id>/delete/",
        views.delete_student_clan_recruitment,
        name="delete_student_clan_recruitment",
    ),
    path(
        "student-recruitment/<int:recruitment_id>/invite/",
        views.invite_student_to_clan,
        name="invite_student_to_clan",
    ),
    path(
        "clan/invitation/<int:invitation_id>/accept/",
        views.accept_clan_invitation,
        name="accept_clan_invitation",
    ),
    path(
        "clan/invitation/<int:invitation_id>/reject/",
        views.reject_clan_invitation,
        name="reject_clan_invitation",
    ),
    path("clan/<int:clan_id>/posts/", views.clan_posts, name="clan_posts"),
    # =========================
    # PROJECTS
    # =========================
    # Personal projects
    path(
        "project/create/",
        views.create_student_project,
        name="create_student_project",
    ),
    path(
        "project/<int:project_id>/",
        views.student_project_detail,
        name="student_project_detail",
    ),
    path(
        "project/<int:project_id>/update/create/",
        views.create_student_project_update,
        name="create_student_project_update",
    ),
    path(
        "project/<int:project_id>/complete/",
        views.complete_student_project,
        name="complete_student_project",
    ),
    # Clan projects
    path(
        "clan/<int:clan_id>/project/create/",
        views.create_clan_project,
        name="create_clan_project",
    ),
    path(
        "clan-project/<int:project_id>/",
        views.clan_project_detail,
        name="clan_project_detail",
    ),
    path(
        "clan-project/<int:project_id>/update/create/",
        views.create_clan_project_update,
        name="create_clan_project_update",
    ),
    path(
        "clan-project/<int:project_id>/complete/",
        views.complete_clan_project,
        name="complete_clan_project",
    ),
    path(
        "messages/<int:message_id>/read/",
        views.mark_admin_message_read,
        name="mark_admin_message_read",
    ),
    path("check-username/", views.check_username, name="check_username"),
    path(
        "projects/<int:project_id>/delete/",
        views.delete_student_project,
        name="delete_student_project",
    ),
    path(
        "project/updates/<int:update_id>/delete/",
        views.delete_student_project_update,
        name="delete_student_project_update",
    ),
    path(
        "clan-project/<int:project_id>/delete/",
        views.delete_clan_project,
        name="delete_clan_project",
    ),
    path(
        "clan-project/updates/<int:update_id>/delete/",
        views.delete_clan_project_update,
        name="delete_clan_project_update",
    ),
    path("check-clan-name/", views.check_clan_name, name="check_clan_name"),
    path(
        "project/<int:project_id>/cover/change/",
        views.change_student_project_cover,
        name="change_student_project_cover",
    ),
    path(
        "clan/project/<int:project_id>/cover/change/",
        views.change_clan_project_cover,
        name="change_clan_project_cover",
    ),
    path(
        "event/<int:event_id>/participate/<str:participation_type>/",
        views.participate_in_event,
        name="participate_in_event",
    ),
    path(
        "event/<int:event_id>/cancel/",
        views.cancel_event_participation,
        name="cancel_event_participation",
    ),
    path("events/", views.events, name="events"),
    path(
        "event/<int:event_id>/clan-members/",
        views.event_clan_members,
        name="event_clan_members",
    ),
    path(
        "event/<int:event_id>/select-clan-members/",
        views.select_event_clan_members,
        name="select_event_clan_members",
    ),
    path(
        "event/<int:event_id>/clan-members/save/",
        views.save_event_clan_members,
        name="save_event_clan_members",
    ),
]

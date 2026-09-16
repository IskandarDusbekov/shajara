from django.urls import include, path, register_converter

from . import collab_views, export_views, maps_views, public_views, quiz, views
from .converters import TreeKeyConverter

register_converter(TreeKeyConverter, "treekey")

urlpatterns = [
    path("", public_views.landing_view, name="landing"),
    path("shajaralar/", public_views.open_index_view, name="open_index"),
    path("shajaralar/karta.png", public_views.open_tree_card_view, name="open_tree_card_default"),
    path("shajaralar/<slug:slug>/", public_views.open_tree_view, name="open_tree"),
    path("shajaralar/<slug:slug>/karta.png", public_views.open_tree_card_view, name="open_tree_card"),
    path("shajaralar/<slug:slug>/<slug:person_slug>/", public_views.open_person_view, name="open_person"),
    path("u/test/<str:token>/", public_views.share_test_view, name="share_test"),
    path("u/test/<str:token>/karta.png", public_views.share_test_png_view, name="share_test_png"),
    path("u/avlod/<str:token>/", public_views.share_avlod_view, name="share_avlod"),
    path("u/avlod/<str:token>/karta.png", public_views.share_avlod_png_view, name="share_avlod_png"),
    path("sitemap.xml", public_views.sitemap_view, name="sitemap"),
    path("robots.txt", public_views.robots_view, name="robots"),
    path("shajaralarim/", views.my_trees_view, name="my_trees"),
    path("royxatdan-otish/", views.register_view, name="register"),
    path("kirish/", views.ShajaraLoginView.as_view(), name="login"),
    path("chiqish/", views.logout_view, name="logout"),
    path("profil/", views.profile_view, name="profile"),
    path("tanishuv/tugadi/", views.tour_done_view, name="tour_done"),

    path("email/tasdiqlash/", views.email_setup_view, name="email_setup"),
    path("email/kod/", views.email_verify_view, name="email_verify"),
    path("parol/tiklash/", views.password_reset_request_view, name="password_reset"),
    path("parol/tiklash/kod/", views.password_reset_verify_view, name="password_reset_verify"),
    path("parol/tiklash/yangi/", views.password_reset_new_view, name="password_reset_new"),

    path("shajara/yangi/", views.tree_create_view, name="tree_create"),
    path("shajara/tiklash/", views.tree_import_create_view, name="tree_import_create"),
    path("shajara/eng-yaxshilari/", views.public_trees_view, name="public_trees"),

    path("shajara/<treekey:tree_key>/", views.index_view, name="index"),
    path("shajara/<treekey:tree_key>/korish/", views.preview_redirect_view, name="preview"),
    path("shajara/<treekey:tree_key>/tartib/", views.tree_layout_view, name="tree_layout"),
    path("shajara/<treekey:tree_key>/haqida/", views.tree_overview_view, name="tree_overview"),
    path("shajara/<treekey:tree_key>/sozlamalar/", views.tree_settings_view, name="tree_settings"),
    path("shajara/<treekey:tree_key>/ochirish/", views.tree_delete_view, name="tree_delete"),
    path("shajara/<treekey:tree_key>/minnatdorchilik/", views.toggle_gratitude_view, name="toggle_gratitude"),
    path("shajara/<treekey:tree_key>/izoh/", views.add_comment_view, name="add_comment"),
    path("shajara/<treekey:tree_key>/shajara.pdf", views.tree_pdf_view, name="tree_pdf"),
    path("shajara/<treekey:tree_key>/shajara.json", views.tree_export_view, name="tree_export"),
    path("shajara/<treekey:tree_key>/rasm/qayd/", export_views.picture_record_view, name="picture_record"),
    path("shajara/<treekey:tree_key>/rasm/korinish/", export_views.preview_upload_view, name="preview_upload"),
    path("shajara/<treekey:tree_key>/rasm/korinish.png", export_views.tree_preview_view, name="tree_preview"),
    path("shajara/<treekey:tree_key>/qoshish/", views.add_relative_view, name="add_relative"),
    path("shajara/<treekey:tree_key>/azolar/", collab_views.members_view, name="tree_members"),
    path("shajara/<treekey:tree_key>/azolar/taklif/", collab_views.invite_create_view, name="invite_create"),
    path("shajara/<treekey:tree_key>/azolar/taklif/<int:pk>/bekor/", collab_views.invite_revoke_view, name="invite_revoke"),
    path("shajara/<treekey:tree_key>/azolar/<int:pk>/", collab_views.member_update_view, name="member_update"),
    path("shajara/<treekey:tree_key>/sinov/", quiz.quiz_view, name="tree_quiz"),
    path("shajara/<treekey:tree_key>/sinov/javob/", quiz.quiz_answer_view, name="tree_quiz_answer"),
    path("shajara/<treekey:tree_key>/shaxs/<int:pk>/", views.person_detail_view, name="person_detail"),
    path("shajara/<treekey:tree_key>/shaxs/<int:pk>/tahrirlash/", views.person_edit_view, name="person_edit"),
    path("shajara/<treekey:tree_key>/shaxs/<int:pk>/ochirish/", views.person_delete_view, name="person_delete"),
    path("shajara/<treekey:tree_key>/shaxs/<int:pk>/hikoya/", views.add_story_view, name="add_story"),

    path("taklif/<str:token>/", collab_views.invite_accept_view, name="invite_accept"),
    path("taklif/<str:token>/rasm.png", export_views.invite_preview_view, name="invite_preview"),
    path("tekshirish/<str:code>/", views.verify_export_view, name="verify_export"),

    path("xaritalar/", maps_views.maps_list_view, name="maps"),
    path("xaritalar/yangi/", maps_views.map_create_view, name="map_create"),
    path("xaritalar/<treekey:key>/", maps_views.map_detail_view, name="map_detail"),
    path("xaritalar/<treekey:key>/sozlamalar/", maps_views.map_settings_view, name="map_settings"),
    path("xaritalar/<treekey:key>/rasm", maps_views.map_image_view, name="map_image"),
    path("xaritalar/<treekey:key>/joy/", maps_views.map_place_save_view, name="map_place_save"),
    path("xaritalar/<treekey:key>/yonalish/", maps_views.map_route_save_view, name="map_route_save"),

    path("qidirish/", views.search_users_view, name="search_users"),
    path("sorov/<str:username>/yuborish/", views.send_request_view, name="send_request"),
    path("sorovlar/", views.requests_view, name="requests"),
    path("sorovlar/<int:pk>/qabul/", views.accept_request_view, name="accept_request"),
    path("sorovlar/<int:pk>/rad/", views.decline_request_view, name="decline_request"),

    path("boshqaruv/", include("shajara.admin_urls")),
]

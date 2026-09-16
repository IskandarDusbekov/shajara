from django.urls import path

from . import admin_views as v

app_name = "boshqaruv"

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("foydalanuvchilar/", v.user_list, name="users"),
    path("foydalanuvchilar/<int:pk>/", v.user_detail, name="user_detail"),
    path("shajaralar/", v.tree_list, name="trees"),
    path("shajaralar/<int:pk>/", v.tree_detail, name="tree_detail"),
    path("moslik/", v.match_list, name="matches"),
    path("moslik/ishga-tushirish/", v.match_run, name="match_run"),
    path("moslik/<int:pk>/", v.match_detail, name="match_detail"),
    path("birlashtirishlar/", v.merge_list, name="merges"),
    path("birlashtirishlar/<int:pk>/", v.merge_detail, name="merge_detail"),
    path("birlashtirishlar/<int:pk>/snapshot.json", v.merge_snapshot, name="merge_snapshot"),
    path("faollik/", v.activity_list, name="activity"),
    path("xarita/", v.region_map, name="map"),
    path("xarita/jonli.json", v.region_map_live, name="map_live"),
    path("seo/", v.seo_pages, name="seo"),
    path("umumiy-shajara/", v.unified_overview, name="unified"),
    path("umumiy-shajara/<int:key>/", v.unified_board, name="unified_board"),
    path("umumiy-shajara/shaxs/<int:pid>/", v.unified_person, name="unified_person"),
]

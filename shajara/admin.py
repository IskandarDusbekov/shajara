from django.contrib import admin

from .models import (
    ConnectionRequest, Family, Person, PersonStory, Tree, TreeComment,
    TreeGratitude,
)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "gender", "birth_year", "added_by", "created_at")
    search_fields = ("first_name", "last_name")
    list_filter = ("gender",)


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("id", "father", "mother", "created_at")


@admin.register(PersonStory)
class PersonStoryAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "author", "created_at")


@admin.register(Tree)
class TreeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "root_person", "visibility", "created_at")
    list_filter = ("visibility",)
    search_fields = ("name", "owner__username")


@admin.register(TreeComment)
class TreeCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "tree", "author", "created_at")


@admin.register(TreeGratitude)
class TreeGratitudeAdmin(admin.ModelAdmin):
    list_display = ("id", "tree", "user", "created_at")


@admin.register(ConnectionRequest)
class ConnectionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "from_user", "from_tree", "to_user", "status", "created_at")
    list_filter = ("status",)


from .models import ActivityLog, MatchCandidate, MatchRun, MergeRecord  # noqa: E402


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "detail", "ip_address")
    list_filter = ("action",)
    search_fields = ("user__username", "detail", "ip_address")
    date_hierarchy = "created_at"


@admin.register(MatchCandidate)
class MatchCandidateAdmin(admin.ModelAdmin):
    list_display = ("pair_key", "score", "status", "reviewed_by", "updated_at")
    list_filter = ("status",)


@admin.register(MatchRun)
class MatchRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "persons_scanned", "pairs_compared", "candidates_found", "candidates_new")


@admin.register(MergeRecord)
class MergeRecordAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "kept_name", "dropped_name", "persons_merged")

from django.contrib import admin

from .models import FeedbackCycle, Project, Response


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description", "leads__username", "leads__email")
    filter_horizontal = ("leads",)


@admin.register(FeedbackCycle)
class FeedbackCycleAdmin(admin.ModelAdmin):
    list_display = ("project", "opens_at", "closes_at", "currently_open")
    list_filter = ("project",)
    search_fields = ("project__name",)
    date_hierarchy = "opens_at"
    readonly_fields = ("token",)

    @admin.display(boolean=True, description="Currently open")
    def currently_open(self, obj):
        return obj.is_open


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("cycle", "score", "created_at")
    list_filter = ("score", "cycle__project")
    search_fields = ("cycle__project__name",)
    date_hierarchy = "created_at"
    readonly_fields = ("cycle", "score", "comment", "created_at", "network_hash", "device_hash")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Responses cannot be deleted directly, but Django's standard project
        # and cycle delete confirmations must be able to describe and perform
        # their established database cascades.
        parent_delete_views = {
            "feedback_project_delete",
            "feedback_feedbackcycle_delete",
        }
        if request.resolver_match and request.resolver_match.url_name in parent_delete_views:
            return True
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

# Register your models here.

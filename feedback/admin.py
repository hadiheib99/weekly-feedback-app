from django.contrib import admin

from .models import FeedbackCycle, Project, Response


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    filter_horizontal = ("leads",)


@admin.register(FeedbackCycle)
class FeedbackCycleAdmin(admin.ModelAdmin):
    list_display = ("project", "opens_at", "closes_at", "is_open")
    readonly_fields = ("token",)


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("cycle", "score", "created_at")
    readonly_fields = ("network_hash", "device_hash", "created_at")

# Register your models here.

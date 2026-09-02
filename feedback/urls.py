from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("feedback/<str:token>/", views.feedback_form, name="feedback_form"),
    path("feedback/<str:token>/thanks/", views.feedback_thanks, name="feedback_thanks"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/project/<int:project_id>/", views.project_dashboard, name="project_dashboard"),
]

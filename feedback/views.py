import hashlib
import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ResponseForm
from .models import FeedbackCycle, Project


def home(request):
    now = timezone.now()
    cycle = FeedbackCycle.objects.filter(project__is_active=True, opens_at__lte=now, closes_at__gte=now).first()
    if cycle:
        return redirect("feedback_form", token=cycle.token)
    return render(request, "feedback/empty.html")


def _hash(value):
    secret = settings.FEEDBACK_HASH_SALT
    return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()


def feedback_form(request, token):
    cycle = get_object_or_404(FeedbackCycle.objects.select_related("project"), token=token)
    if not cycle.is_open:
        return render(request, "feedback/closed.html", {"cycle": cycle}, status=403)

    device_id = request.COOKIES.get("pulse_device") or uuid.uuid4().hex
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    network = forwarded or request.META.get("REMOTE_ADDR", "unknown")
    network_hash, device_hash = _hash(network), _hash(device_id)
    duplicate = cycle.responses.filter(network_hash=network_hash).exists() or cycle.responses.filter(device_hash=device_hash).exists()

    if request.method == "POST":
        if duplicate:
            return render(request, "feedback/unavailable.html", status=409)
        form = ResponseForm(request.POST)
        if form.is_valid():
            response = form.save(commit=False)
            response.cycle = cycle
            response.network_hash = network_hash
            response.device_hash = device_hash
            try:
                with transaction.atomic():
                    response.save()
            except IntegrityError:
                return render(request, "feedback/unavailable.html", status=409)
            result = redirect("feedback_thanks", token=token)
            result.set_cookie("pulse_device", device_id, max_age=60 * 60 * 24 * 365, httponly=True, samesite="Lax", secure=not settings.DEBUG)
            return result
    else:
        if duplicate:
            return render(request, "feedback/unavailable.html", status=409)
        form = ResponseForm()
    return render(request, "feedback/form.html", {"cycle": cycle, "form": form})


def feedback_thanks(request, token):
    cycle = get_object_or_404(FeedbackCycle.objects.select_related("project"), token=token)
    return render(request, "feedback/thanks.html", {"cycle": cycle})


def _visible_projects(user):
    if user.is_staff:
        return Project.objects.filter(is_active=True)
    return Project.objects.filter(is_active=True, leads=user)


@login_required
def dashboard(request):
    projects = _visible_projects(request.user).annotate(
        response_count=Count("cycles__responses"), average_score=Avg("cycles__responses__score")
    )
    return render(request, "feedback/dashboard.html", {"projects": projects, "is_admin": request.user.is_staff})


@login_required
def project_dashboard(request, project_id):
    project = get_object_or_404(_visible_projects(request.user), pk=project_id)
    cycle = project.cycles.annotate(average=Avg("responses__score"), total=Count("responses")).first()
    if not cycle:
        raise Http404("No feedback cycle exists for this project")
    distribution = {item["score"]: item["total"] for item in cycle.responses.values("score").annotate(total=Count("id"))}
    bars = [{"score": score, "count": distribution.get(score, 0)} for score in range(1, 6)]
    return render(request, "feedback/project_dashboard.html", {"project": project, "cycle": cycle, "bars": bars, "is_admin": request.user.is_staff})

# Create your views here.

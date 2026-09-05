import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ResponseForm
from .models import FeedbackCycle, Project


MISSING_NETWORK_IDENTIFIER = "missing-network-address"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def home(request):
    now = timezone.now()
    cycle = FeedbackCycle.objects.filter(
        project__is_active=True,
        opens_at__lte=now,
        closes_at__gte=now,
    ).order_by("-opens_at", "id").first()
    if cycle:
        return redirect("feedback_form", token=cycle.token)
    return render(request, "feedback/empty.html")


def _hash(value):
    secret = settings.FEEDBACK_HASH_SALT
    return hashlib.sha256(f"{secret}:{value}".encode()).hexdigest()


def _network_identifier(request):
    # Client-supplied forwarded headers are intentionally ignored. A deployment
    # behind a trusted proxy must arrange for REMOTE_ADDR to contain the client.
    return request.META.get("REMOTE_ADDR") or MISSING_NETWORK_IDENTIFIER


def feedback_form(request, token):
    cycle = get_object_or_404(FeedbackCycle.objects.select_related("project"), token=token)
    if not cycle.project.is_active:
        return render(request, "feedback/unavailable.html", status=403)

    now = timezone.now()
    if now < cycle.opens_at:
        return render(request, "feedback/unavailable.html", {"future_cycle": True}, status=403)
    if now > cycle.closes_at:
        return render(request, "feedback/closed.html", {"cycle": cycle}, status=403)

    device_id = request.COOKIES.get("pulse_device") or secrets.token_urlsafe(32)
    network = _network_identifier(request)
    network_hash, device_hash = _hash(network), _hash(device_id)
    duplicate = cycle.responses.filter(network_hash=network_hash).exists() or cycle.responses.filter(device_hash=device_hash).exists()

    if request.method == "POST":
        if duplicate:
            return render(request, "feedback/unavailable.html", {"duplicate_submission": True}, status=409)
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
                return render(request, "feedback/unavailable.html", {"duplicate_submission": True}, status=409)
            result = redirect("feedback_thanks", token=token)
            result.set_cookie(
                "pulse_device",
                device_id,
                max_age=DEVICE_COOKIE_MAX_AGE,
                path="/",
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
            return result
    else:
        if duplicate:
            return render(request, "feedback/unavailable.html", {"duplicate_submission": True}, status=409)
        form = ResponseForm()
    return render(request, "feedback/form.html", {"cycle": cycle, "form": form})


def feedback_thanks(request, token):
    cycle = get_object_or_404(FeedbackCycle.objects.select_related("project"), token=token)
    return render(request, "feedback/thanks.html", {"cycle": cycle})


def _visible_projects(user):
    if user.is_staff:
        return Project.objects.all()
    return Project.objects.filter(leads=user)


@login_required
def dashboard(request):
    projects = (
        _visible_projects(request.user)
        .filter(is_active=True)
        .annotate(
            response_count=Count("cycles__responses", distinct=True),
            average_score=Avg("cycles__responses__score"),
        )
        .order_by(Lower("name"), "id")
        .prefetch_related("leads")
    )
    return render(request, "feedback/dashboard.html", {"projects": projects, "is_admin": request.user.is_staff})


@login_required
def project_dashboard(request, project_id):
    project = get_object_or_404(_visible_projects(request.user), pk=project_id)
    cycle = (
        project.cycles.annotate(average=Avg("responses__score"), total=Count("responses"))
        .order_by("-opens_at", "-id")
        .first()
    )
    distribution = {}
    comments = []
    if cycle:
        distribution = {
            item["score"]: item["total"]
            for item in cycle.responses.values("score").annotate(total=Count("id"))
        }
        comments = cycle.responses.exclude(comment__regex=r"^\s*$").order_by("-created_at", "-id").values(
            "comment", "score", "created_at"
        )
    bars = [{"score": score, "count": distribution.get(score, 0)} for score in range(1, 6)]
    context = {
        "project": project,
        "has_cycle": cycle is not None,
        "opens_at": cycle.opens_at if cycle else None,
        "closes_at": cycle.closes_at if cycle else None,
        "response_total": cycle.total if cycle else None,
        "average_score": cycle.average if cycle else None,
        "bars": bars if cycle else [],
        "comments": comments,
        "is_admin": request.user.is_staff,
    }
    return render(request, "feedback/project_dashboard.html", context)

# Create your views here.

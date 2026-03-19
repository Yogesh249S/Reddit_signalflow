"""
apps/signals/admin.py — add this APIAccessRequest admin
=========================================================
One-click approve: creates Django user, generates token, sends email.
"""

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
import secrets
import string

# from .models import APIAccessRequest


def _generate_api_token():
    """Generate a secure 40-char hex token."""
    return secrets.token_hex(20)


def _send_approval_email(email, name, token):
    subject = "Your SignalFlow API token"
    body = f"""Hi {name},

Your SignalFlow API access is approved. Here is your token:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR API TOKEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {token}

Keep this private — it grants full API access.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK START
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl https://signalflo.in/api/v1/trending/ \\
  -H "Authorization: Token {token}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PYTHON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import requests

headers = {{"Authorization": "Token {token}"}}
r = requests.get(
    "https://signalflo.in/api/v1/trending/",
    params={{"window_minutes": 120}},
    headers=headers
)
print(r.json())

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RATE LIMITS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
100 requests / minute. Data refreshes every 30s.

Full docs: https://signalflo.in/docs/

Questions? Reply to this email.

— Yogesh
SignalFlow
"""
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "yogesh249@proton.me"),
        recipient_list=[email],
        fail_silently=False,
    )


@admin.action(description="✅ Approve selected requests — create user + send API token")
def approve_requests(modeladmin, request, queryset):
    from rest_framework.authtoken.models import Token

    approved = 0

    for req in queryset.filter(status="pending"):
        # Generate username from email prefix, ensure unique
        base_username = req.email.split("@")[0][:20].lower().replace(".", "_")
        username = base_username
        counter  = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1

        # Create Django user (password not needed — token auth only)
        user = User.objects.create_user(
            username=username,
            email=req.email,
            first_name=req.name.split()[0] if req.name else "",
        )

        # Generate DRF token
        token, _ = Token.objects.get_or_create(user=user)

        # Update request
        req.status      = "approved"
        req.user        = user
        req.reviewed_at = timezone.now()
        req.save()

        # Send token email
        try:
            _send_approval_email(req.email, req.name, token.key)
            approved += 1
        except Exception as e:
            modeladmin.message_user(
                request,
                f"Token created for {req.email} but email failed: {e}",
                level="warning",
            )
            approved += 1

    if approved:
        modeladmin.message_user(request, f"Approved {approved} request(s) and sent API tokens.")


@admin.action(description="❌ Reject selected requests")
def reject_requests(modeladmin, request, queryset):
    updated = queryset.filter(status="pending").update(
        status="rejected",
        reviewed_at=timezone.now(),
    )
    modeladmin.message_user(request, f"Rejected {updated} request(s).")


# @admin.register(APIAccessRequest)
class APIAccessRequestAdmin(admin.ModelAdmin):
    list_display  = ("email", "name", "company", "use_case", "status", "created_at")
    list_filter   = ("status", "use_case")
    search_fields = ("email", "name", "company")
    readonly_fields = ("created_at", "reviewed_at", "user")
    actions       = [approve_requests, reject_requests]

    fieldsets = (
        ("Applicant", {
            "fields": ("name", "email", "company", "use_case", "description")
        }),
        ("Status", {
            "fields": ("status", "created_at", "reviewed_at", "user")
        }),
    )

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending email notifications via Resend"""

    @staticmethod
    def _get_user_display_name(user):
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        elif user.email:
            return user.email.split('@')[0]
        else:
            return "User"

    @staticmethod
    def _send_email(subject, recipient, html_template, context, plain_message=None, from_email=None):
        """
        Generic method to send email via Resend.
        Automatically switches to a verified domain if needed.
        """
        from django.conf import settings
        import logging

        logger = logging.getLogger(__name__)

        try:
            html_message = render_to_string(html_template, context)

            if not plain_message:
                plain_message = strip_tags(html_message)

            # Use the provided from_email or fallback to settings
            if not from_email:
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@datican.org")

            # Ensure the from_email uses a verified domain in development
            verified_domains = ["datican.org", "repo.datican.org"]
            domain = from_email.split("@")[-1]
            if domain not in verified_domains:
                logger.warning(
                    f"From email '{from_email}' is not a verified domain. "
                    f"Switching to default verified domain 'no-reply@datican.org' to prevent 403."
                )
                from_email = "no-reply@datican.org"

            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=from_email,
                recipient_list=[recipient],
                fail_silently=False,
            )

            logger.info(f"Email sent to {recipient}: {subject}")
            return True

        except Exception as e:
            logger.exception(f"Email sending failed to {recipient} with subject '{subject}'")
            raise

    # =========================
    # User Emails
    # =========================
    @staticmethod
    def send_acknowledgment_email(request):
        subject = f"Data Request Received - #{request.id}"
        context = {
            'user': request.user,
            'request': request,
            'dataset': request.dataset,
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(request.user),
        }
        return EmailService._send_email(
            subject, request.user.email,
            'emails/requests/acknowledgment.html', context
        )

    @staticmethod
    def send_approval_email(request):
        """Send approval email with direct download link"""
        subject = f"🎉 Data Request Approved - #{request.id}"
        download_url = settings.SITE_URL + reverse(
            'dataset_download', args=[request.dataset.id]
        )
        context = {
            'user': request.user,
            'request': request,
            'download_url': download_url,
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(request.user),
            'approval_date': request.approved_date or timezone.now(),
        }
        return EmailService._send_email(
            subject, request.user.email,
            'emails/requests/approval.html', context
        )

    @staticmethod
    def send_rejection_email(request, rejected_by, rejection_reason, role='manager'):
        """Send rejection email to user"""
        subject = f"📋 Update on Your Data Request - #{request.id}"
        new_request_url = settings.SITE_URL + reverse(
            'dataset_request', args=[request.dataset.id]
        )
        context = {
            'user': request.user,
            'request': request,
            'decision_by': rejected_by,
            'decision_position': role,
            'rejection_reason': rejection_reason,
            'site_name': settings.SITE_NAME,
            'contact_email': settings.CONTACT_EMAIL,
            'new_request_url': new_request_url,
            'user_display_name': EmailService._get_user_display_name(request.user),
            'decision_by_name': EmailService._get_user_display_name(rejected_by),
        }
        return EmailService._send_email(
            subject, request.user.email,
            'emails/requests/rejection.html', context
        )

    @staticmethod
    def send_status_update_email(request, previous_status, updated_by):
        subject = f"🔄 Data Request Status Update - #{request.id}"
        status_map = {
            'pending': 'Pending',
            'manager_review': 'Under Manager Review',
            'director_review': 'Under Director Review',
            'approved': 'Approved',
            'rejected': 'Rejected',
        }
        context = {
            'user': request.user,
            'request': request,
            'previous_status': status_map.get(previous_status, previous_status),
            'current_status': request.get_status_display(),
            'updated_by': updated_by,
            'update_date': request.approved_date or timezone.now(),
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(request.user),
            'updated_by_name': EmailService._get_user_display_name(updated_by),
        }
        return EmailService._send_email(
            subject, request.user.email,
            'emails/requests/status_update.html', context
        )

    # =========================
    # Staff Emails
    # =========================
    @staticmethod
    def send_staff_notification(request, staff_member, role='manager'):
        if role == 'manager':
            subject = f"New Data Request for Review - #{request.id}"
            review_url = settings.SITE_URL + reverse('manager_review', args=[request.id])
        else:
            subject = f"Data Request Ready for Final Approval - #{request.id}"
            review_url = settings.SITE_URL + reverse('director_review', args=[request.id])
        context = {
            'staff_member': staff_member,
            'request': request,
            'review_url': review_url,
            'site_name': settings.SITE_NAME,
            'staff_display_name': EmailService._get_user_display_name(staff_member),
            'user_display_name': EmailService._get_user_display_name(request.user),
            'requester_email': request.user.email,
        }
        return EmailService._send_email(
            subject, staff_member.email,
            'emails/requests/notification_to_staff.html', context
        )

    # =========================
    # Misc Emails
    # =========================
    @staticmethod
    def send_welcome_email(user):
        subject = f"👋 Welcome to {settings.SITE_NAME}!"
        login_url = settings.SITE_URL + reverse('account_login')
        context = {
            'user': user,
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(user),
            'login_url': login_url,
        }
        return EmailService._send_email(
            subject, user.email,
            'emails/welcome.html', context
        )

    @staticmethod
    def send_test_email(recipient_email="test@example.com"):
        subject = f"✅ Resend Test Email - {settings.SITE_NAME}"
        plain_message = f"This is a test email from {settings.SITE_NAME} at {timezone.now()}."
        context = {
            'site_name': settings.SITE_NAME,
            'current_time': timezone.now(),
        }
        return EmailService._send_email(
            subject, recipient_email,
            'emails/test.html', context,
            plain_message=plain_message
        )

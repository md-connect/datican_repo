from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from anymail.exceptions import AnymailError
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending email notifications via Resend"""
    
    @staticmethod
    def _get_user_display_name(user):
        """Helper to get user display name"""
        if user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        elif user.email:
            return user.email.split('@')[0]
        else:
            return "User"
    
    @staticmethod
    def _send_email(subject, recipient, html_template, context, plain_message=None):
        """Generic method to send email via Resend"""
        try:
            html_message = render_to_string(html_template, context)
            
            if not plain_message:
                plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            
            logger.info(f"Email sent to {recipient}: {subject}")
            return True
            
        except Exception as e:
            logger.exception("Email sending failed")
            raise

    @staticmethod
    def send_acknowledgment_email(request):
        """Send acknowledgment email to user after request submission"""
        context = {
            'user': request.user,
            'request': request,
            'dataset': request.dataset,
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(request.user),
        }
        
        subject = f"Data Request Received - #{request.id}"
        return EmailService._send_email(
            subject=subject,
            recipient=request.user.email,
            html_template='emails/requests/acknowledgment.html',
            context=context
        )
    
    @staticmethod
    def send_staff_notification(request, staff_member, role='manager'):
        """Send notification to staff (manager or director) about new request"""
        try:
            if role == 'manager':
                subject = f"New Data Request for Review - #{request.id}"
                review_url = settings.SITE_URL + reverse('manager_review', args=[request.id])

            else:  # director
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
                subject=subject,
                recipient=staff_member.email,
                html_template='emails/requests/notification_to_staff.html',
                context=context
            )
            
        except Exception as e:
            logger.error(f"Failed to prepare staff notification for request #{request.id}: {str(e)}")
            return False
    
    @staticmethod
    def send_approval_email(request):
        """Send approval email to user with download link"""
        try:
            # Generate download URL
            try:
                download_url = settings.SITE_URL + reverse(
                    'dataset_download',
                    args=[request.dataset.id]
                )

            except:
                try:
                    download_url = settings.SITE_URL + reverse(
                        'dataset_download',
                        args=[request.dataset.id]
                    )

                except:
                    download_url = f"{settings.SITE_URL}/datasets/{request.dataset.id}/download/{request.id}/"
            
            context = {
                'user': request.user,
                'request': request,
                'download_url': download_url,
                'site_name': settings.SITE_NAME,
                'support_email': settings.SUPPORT_EMAIL,
                'user_display_name': EmailService._get_user_display_name(request.user),
                'approval_date': request.approved_date or timezone.now(),
            }
            
            subject = f"🎉 Data Request Approved - #{request.id}"
            
            return EmailService._send_email(
                subject=subject,
                recipient=request.user.email,
                html_template='emails/requests/approval.html',
                context=context
            )
            
        except Exception as e:
            logger.error(f"Failed to prepare approval email for request #{request.id}: {str(e)}")
            return False
    
    @staticmethod
    def send_rejection_email(request, rejected_by, rejection_reason, role='manager'):
        """Send rejection email to user"""
        context = {
            'user': request.user,
            'request': request,
            'decision_by': rejected_by,
            'decision_position': role,
            'rejection_reason': rejection_reason,
            'site_name': settings.SITE_NAME,
            'contact_email': settings.CONTACT_EMAIL,
            'new_request_url': settings.SITE_URL + reverse('request_data', args=[request.dataset.id]),
            'user_display_name': EmailService._get_user_display_name(request.user),
            'decision_by_name': EmailService._get_user_display_name(rejected_by),
        }
        
        subject = f"📋 Update on Your Data Request - #{request.id}"
        
        return EmailService._send_email(
            subject=subject,
            recipient=request.user.email,
            html_template='emails/requests/rejection.html',
            context=context
        )
    
    @staticmethod
    def send_status_update_email(request, previous_status, updated_by):
        """Send email when request status changes"""
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
        
        subject = f"🔄 Data Request Status Update - #{request.id}"
        
        return EmailService._send_email(
            subject=subject,
            recipient=request.user.email,
            html_template='emails/requests/status_update.html',
            context=context
        )
    
    @staticmethod
    def send_change_request_email(data_request, requested_by, comments):
        """Send change request email to researcher"""
        context = {
            'data_request': data_request,
            'user': data_request.user,
            'requested_by': requested_by,
            'comments': comments,
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(data_request.user),
            'requested_by_name': EmailService._get_user_display_name(requested_by),
        }
        
        subject = f"📝 Changes Requested for Data Request #{data_request.id}"
        
        return EmailService._send_email(
            subject=subject,
            recipient=data_request.user.email,
            html_template='emails/requests/change_request.html',
            context=context
        )
    
    @staticmethod
    def send_welcome_email(user):
        """Send welcome email to new user"""
        context = {
            'user': user,
            'site_name': settings.SITE_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'user_display_name': EmailService._get_user_display_name(user),
            'login_url': settings.SITE_URL + reverse('account_login'),
        }
        
        subject = f"👋 Welcome to {settings.SITE_NAME}!"
        
        return EmailService._send_email(
            subject=subject,
            recipient=user.email,
            html_template='emails/welcome.html',
            context=context
        )
    
    @staticmethod
    def send_test_email(recipient_email="test@example.com"):
        """Send a test email to verify Resend configuration"""
        context = {
            'site_name': settings.SITE_NAME,
            'current_time': timezone.now(),
        }
        
        subject = f"✅ Resend Test Email - {settings.SITE_NAME}"
        plain_message = f"This is a test email sent via Resend from {settings.SITE_NAME} at {timezone.now()}."
        
        return EmailService._send_email(
            subject=subject,
            recipient=recipient_email,
            html_template='emails/test.html',
            context=context,
            plain_message=plain_message
        )
    
    @staticmethod
    def debug_send_test_email(request_obj, email_type='acknowledgment'):
        """Debug method to test email sending"""
        try:
            if email_type == 'acknowledgment':
                return EmailService.send_acknowledgment_email(request_obj)
            elif email_type == 'staff_notification':
                from accounts.models import CustomUser
                staff = CustomUser.objects.filter(is_staff=True).first()
                if staff:
                    return EmailService.send_staff_notification(request_obj, staff, 'manager')
            elif email_type == 'approval':
                return EmailService.send_approval_email(request_obj)
            elif email_type == 'rejection':
                return EmailService.send_rejection_email(request_obj, request_obj.user, "Test rejection reason", 'manager')
            elif email_type == 'status_update':
                return EmailService.send_status_update_email(request_obj, 'pending', request_obj.user)
            elif email_type == 'change_request':
                return EmailService.send_change_request_email(request_obj, request_obj.user, "Test change request comments")
            elif email_type == 'welcome':
                return EmailService.send_welcome_email(request_obj.user if hasattr(request_obj, 'user') else request_obj)
            elif email_type == 'test':
                return EmailService.send_test_email(request_obj.user.email if hasattr(request_obj, 'user') else 'test@example.com')
            
            return False
        except Exception as e:
            logger.error(f"Debug email failed: {e}")
            return False
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Service for sending email notifications related to data requests"""
    
    @staticmethod
    def send_acknowledgment_email(request):
        """Send acknowledgment email to user after request submission"""
        try:
            subject = f"Data Request Received - #{request.id}"
            
            context = {
                'user': request.user,
                'request': request,
                'dataset': request.dataset,
                'site_name': settings.SITE_NAME,
                'support_email': settings.SUPPORT_EMAIL,
            }
            
            html_message = render_to_string('emails/requests/acknowledgment.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=False,
            )
            
            logger.info(f"Acknowledgment email sent for request #{request.id} to {request.user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send acknowledgment email for request #{request.id}: {str(e)}")
            return False
    
    @staticmethod
    def send_staff_notification(request, staff_member, role='manager'):
        """Send notification to staff (manager or director) about new request"""
        try:
            if role == 'manager':
                subject = f"New Data Request for Review - #{request.id}"
                review_url = settings.SITE_URL + reverse('review_request', args=[request.id])
            else:  # director
                subject = f"Data Request Ready for Final Approval - #{request.id}"
                review_url = settings.SITE_URL + reverse('director_review', args=[request.id])
            
            context = {
                'staff_member': staff_member,
                'request': request,
                'review_url': review_url,
                'site_name': settings.SITE_NAME,
            }
            
            html_message = render_to_string('emails/requests/notification_to_staff.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[staff_member.email],
                fail_silently=False,
            )
            
            logger.info(f"Staff notification sent to {staff_member.email} for request #{request.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send staff notification for request #{request.id}: {str(e)}")
            return False
    
    @staticmethod
    def send_approval_email(request):
        """Send approval email to user with download link"""
        try:
            subject = f"Data Request Approved - #{request.id}"
            
            # Generate download URL
            download_url = settings.SITE_URL + reverse('download_dataset', args=[request.dataset.id, request.id])
            
            context = {
                'user': request.user,
                'request': request,
                'download_url': download_url,
                'site_name': settings.SITE_NAME,
                'support_email': settings.SUPPORT_EMAIL,
            }
            
            html_message = render_to_string('emails/requests/approval.html', context)
            plain_message = strip_tags(html_message)
            
            # Create email with attachment if needed
            email = EmailMultiAlternatives(
                subject=subject,
                body=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[request.user.email],
            )
            email.attach_alternative(html_message, "text/html")
            
            # Optional: Attach data use agreement
            # if settings.DATA_USE_AGREEMENT_PATH:
            #     with open(settings.DATA_USE_AGREEMENT_PATH, 'rb') as f:
            #         email.attach('Data_Use_Agreement.pdf', f.read(), 'application/pdf')
            
            email.send(fail_silently=False)
            
            logger.info(f"Approval email sent for request #{request.id} to {request.user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send approval email for request #{request.id}: {str(e)}")
            return False
    
    @staticmethod
    def send_rejection_email(request, rejected_by, rejection_reason, role='manager'):
        """Send rejection email to user"""
        try:
            subject = f"Update on Your Data Request - #{request.id}"
            
            context = {
                'user': request.user,
                'request': request,
                'decision_by': rejected_by,
                'decision_position': role,
                'rejection_reason': rejection_reason,
                'site_name': settings.SITE_NAME,
                'manager_email': settings.MANAGER_EMAIL,
                'director_email': settings.DIRECTOR_EMAIL,
                'contact_email': settings.CONTACT_EMAIL,
                'new_request_url': settings.SITE_URL + reverse('request_data', args=[request.dataset.id]),
            }
            
            html_message = render_to_string('emails/requests/rejection.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=False,
            )
            
            logger.info(f"Rejection email sent for request #{request.id} to {request.user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send rejection email for request #{request.id}: {str(e)}")
            return False
    
    @staticmethod
    def send_status_update_email(request, previous_status, updated_by):
        """Send email when request status changes"""
        try:
            subject = f"Data Request Status Update - #{request.id}"
            
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
                'updated_by': updated_by.get_full_name() or updated_by.username,
                'update_date': request.approved_date or timezone.now(),
                'site_name': settings.SITE_NAME,
                'support_email': settings.SUPPORT_EMAIL,
            }
            
            html_message = render_to_string('emails/requests/status_update.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=subject,
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[request.user.email],
                fail_silently=False,
            )
            
            logger.info(f"Status update email sent for request #{request.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send status update email for request #{request.id}: {str(e)}")
            return False
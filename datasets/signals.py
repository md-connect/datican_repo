from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import DataRequest
from datasets.utils.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=DataRequest)
def handle_request_creation(sender, instance, created, **kwargs):
    """Handle actions when a new request is created"""
    if created:
        # Send acknowledgment email to user
        EmailService.send_acknowledgment_email(instance)
        
        # Find and notify manager (you might need to implement manager finding logic)
        # Example: manager = User.objects.filter(groups__name='Data Managers').first()
        # if manager:
        #     instance.manager = manager
        #     instance.save()
        #     EmailService.send_staff_notification(instance, manager, 'manager')
        
        logger.info(f"New data request #{instance.id} created by {instance.user.email}")

@receiver(pre_save, sender=DataRequest)
def handle_status_change(sender, instance, **kwargs):
    """Handle status changes and send appropriate emails"""
    if instance.pk:
        try:
            old_instance = DataRequest.objects.get(pk=instance.pk)
            old_status = old_instance.status
            
            # If status changed
            if old_status != instance.status:
                logger.info(f"Request #{instance.id} status changed from {old_status} to {instance.status}")
                
                # Handle specific status transitions
                if instance.status == 'manager_review' and instance.manager:
                    # Notify manager
                    EmailService.send_staff_notification(instance, instance.manager, 'manager')
                
                elif instance.status == 'director_review' and instance.director:
                    # Notify director
                    EmailService.send_staff_notification(instance, instance.director, 'director')
                    # Also notify user about progress
                    EmailService.send_status_update_email(instance, old_status, instance.manager)
                
                elif instance.status == 'approved':
                    # Record approval date
                    instance.approved_date = timezone.now()
                    # Send approval email with download link
                    EmailService.send_approval_email(instance)
                
                elif instance.status == 'rejected':
                    # Determine who rejected and send rejection email
                    if instance.manager_action == 'rejected':
                        rejected_by = instance.manager
                        rejection_reason = instance.data_manager_comment
                        role = 'manager'
                    else:  # director rejected
                        rejected_by = instance.director
                        rejection_reason = instance.director_comment
                        role = 'director'
                    
                    if rejected_by and rejection_reason:
                        EmailService.send_rejection_email(instance, rejected_by, rejection_reason, role)
            
            # Handle manager/director actions
            if old_instance.manager_action != instance.manager_action and instance.manager_action == 'recommended':
                instance.status = 'director_review'
                instance.manager_review_date = timezone.now()
            
            if old_instance.director_action != instance.director_action:
                if instance.director_action == 'approved':
                    instance.status = 'approved'
                    instance.approved_date = timezone.now()
                elif instance.director_action == 'rejected':
                    instance.status = 'rejected'
                    
        except DataRequest.DoesNotExist:
            pass  # New instance, no old status to compare
# accounts/management/commands/setup_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.apps import apps

class Command(BaseCommand):
    help = 'Creates default role groups and permissions'
    
    def handle(self, *args, **options):
        # Get or create groups
        admin_group, created = Group.objects.get_or_create(name='Admins')
        data_manager_group, created = Group.objects.get_or_create(name='Data Managers')
        director_group, created = Group.objects.get_or_create(name='Directors')
        
        # Get all model permissions
        all_perms = Permission.objects.all()
        
        # Admin gets all permissions
        admin_group.permissions.set(all_perms)
        
        # Data Manager permissions - can review data requests
        data_manager_perms = Permission.objects.filter(
            codename__in=[
                'view_datarequest', 'change_datarequest', 
                'review_datarequest', 'add_datarequest'
            ]
        )
        data_manager_group.permissions.set(data_manager_perms)
        
        # Director permissions - can approve data requests
        director_perms = Permission.objects.filter(
            codename__in=[
                'view_datarequest', 'change_datarequest', 
                'approve_datarequest', 'add_datarequest'
            ]
        )
        director_group.permissions.set(director_perms)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created role groups and permissions')
        )
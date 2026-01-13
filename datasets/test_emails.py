import os
import django
from django.test import TestCase
from django.core import mail
from your_app.models import DataRequest, User, Dataset
from utils.email_service import EmailService

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datican_repo.settings')
django.setup()

class EmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.dataset = Dataset.objects.create(
            title='Test Dataset',
            description='Test description'
        )
        self.request = DataRequest.objects.create(
            user=self.user,
            dataset=self.dataset,
            institution='Test University',
            project_title='Test Project',
            project_description='Test description'
        )
    
    def test_acknowledgment_email(self):
        """Test acknowledgment email sending"""
        success = EmailService.send_acknowledgment_email(self.request)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Data Request Received', mail.outbox[0].subject)
    
    def test_approval_email(self):
        """Test approval email with download link"""
        self.request.status = 'approved'
        self.request.save()
        
        success = EmailService.send_approval_email(self.request)
        self.assertTrue(success)
        self.assertIn('Data Request Approved', mail.outbox[0].subject)
    
    def tearDown(self):
        self.user.delete()
        self.dataset.delete()
        self.request.delete()
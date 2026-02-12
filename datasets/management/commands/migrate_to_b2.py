# datasets/management/commands/migrate_to_b2.py
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from django.utils import timezone
from datasets.models import Dataset, Thumbnail, DataRequest
import os
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Migrate existing local files to Backblaze B2'
    
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Dry run (no actual upload)')
        parser.add_argument('--model', choices=['datasets', 'thumbnails', 'requests'], default='all')
        parser.add_argument('--verify', action='store_true', help='Verify uploads by checking existence in B2')
    
    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.verify = options.get('verify', False)
        model = options['model']
        
        if self.dry_run:
            self.stdout.write(self.style.WARNING('🧪 DRY RUN - No files will be uploaded'))
        
        self.stdout.write(self.style.SUCCESS('🚀 Starting migration to Backblaze B2...'))
        
        # Migrate datasets
        if model in ['all', 'datasets']:
            self.migrate_datasets()
        
        # Migrate thumbnails
        if model in ['all', 'thumbnails']:
            self.migrate_thumbnails()
        
        # Migrate request documents
        if model in ['all', 'requests']:
            self.migrate_requests()
    
    def verify_b2_upload(self, file_field):
        """Verify file exists in B2 after upload"""
        if not self.verify:
            return True
        try:
            return file_field.storage.exists(file_field.name)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  ⚠ Verification failed: {e}'))
            return False
    
    def migrate_datasets(self):
        datasets = Dataset.objects.exclude(file='').exclude(file__isnull=True)
        total = datasets.count()
        success = 0
        failed = 0
        skipped = 0
        
        self.stdout.write(f"\n📊 Found {total} datasets with files")
        
        for idx, dataset in enumerate(datasets, 1):
            progress = f"[{idx}/{total}]"
            
            try:
                if not dataset.file or not hasattr(dataset.file, 'path'):
                    self.stdout.write(self.style.WARNING(f'{progress} Dataset {dataset.id}: No local file path'))
                    skipped += 1
                    continue
                
                local_path = dataset.file.path
                
                if not os.path.exists(local_path):
                    self.stdout.write(self.style.WARNING(f'{progress} Dataset {dataset.id}: File not found: {local_path}'))
                    skipped += 1
                    continue
                
                file_size = os.path.getsize(local_path)
                self.stdout.write(f"{progress} Dataset {dataset.id}: {dataset.file.name} ({self._format_size(file_size)})")
                
                if self.dry_run:
                    skipped += 1
                    continue
                
                # Upload to B2
                with open(local_path, 'rb') as f:
                    dataset.file.save(
                        dataset.file.name,
                        File(f),
                        save=False
                    )
                
                # Verify upload
                if self.verify_b2_upload(dataset.file):
                    # Store B2 metadata
                    try:
                        storage = dataset.file.storage
                        if hasattr(storage, 'bucket'):
                            dataset.b2_file_id = f"{storage.bucket.name}/{dataset.file.name}"
                            dataset.b2_file_info = {
                                'migrated_at': timezone.now().isoformat(),
                                'original_path': local_path,
                                'original_size': file_size,
                                'verified': True
                            }
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'  ⚠ Failed to store metadata: {e}'))
                    
                    # Update file size
                    dataset.size = file_size
                    dataset.save()
                    
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Uploaded to B2 and verified'))
                    success += 1
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Upload verification failed'))
                    failed += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'{progress} ✗ Failed: {str(e)}'))
                failed += 1
        
        # Summary
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Datasets migration complete: "
            f"{success} uploaded, {failed} failed, {skipped} skipped"
        ))
    
    def migrate_thumbnails(self):
        thumbnails = Thumbnail.objects.exclude(image='').exclude(image__isnull=True)
        total = thumbnails.count()
        success = 0
        failed = 0
        skipped = 0
        
        self.stdout.write(f"\n📊 Found {total} thumbnails")
        
        for idx, thumb in enumerate(thumbnails, 1):
            progress = f"[{idx}/{total}]"
            
            try:
                if not thumb.image or not hasattr(thumb.image, 'path'):
                    skipped += 1
                    continue
                
                local_path = thumb.image.path
                
                if not os.path.exists(local_path):
                    self.stdout.write(self.style.WARNING(f'{progress} Thumbnail {thumb.id}: File not found'))
                    skipped += 1
                    continue
                
                self.stdout.write(f"{progress} Thumbnail {thumb.id}: {thumb.image.name}")
                
                if self.dry_run:
                    skipped += 1
                    continue
                
                with open(local_path, 'rb') as f:
                    thumb.image.save(
                        thumb.image.name,
                        File(f),
                        save=False
                    )
                    thumb.save()
                
                self.stdout.write(self.style.SUCCESS(f'  ✓ Uploaded to B2'))
                success += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'{progress} ✗ Failed: {str(e)}'))
                failed += 1
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Thumbnails migration complete: "
            f"{success} uploaded, {failed} failed, {skipped} skipped"
        ))
    
    def migrate_requests(self):
        requests = DataRequest.objects.filter(
            models.Q(form_submission__isnull=False) |
            models.Q(ethical_approval_proof__isnull=False)
        )
        total = requests.count()
        success = 0
        failed = 0
        skipped = 0
        
        self.stdout.write(f"\n📊 Found {total} requests with documents")
        
        for idx, req in enumerate(requests, 1):
            progress = f"[{idx}/{total}]"
            
            # Migrate form submission
            if req.form_submission:
                result = self._migrate_request_file(req, req.form_submission, 'form', progress)
                if result == 'success':
                    success += 1
                elif result == 'failed':
                    failed += 1
                else:
                    skipped += 1
            
            # Migrate ethical approval proof
            if req.ethical_approval_proof:
                result = self._migrate_request_file(req, req.ethical_approval_proof, 'ethics', progress)
                if result == 'success':
                    success += 1
                elif result == 'failed':
                    failed += 1
                else:
                    skipped += 1
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Request documents migration complete: "
            f"{success} uploaded, {failed} failed, {skipped} skipped"
        ))
    
    def _migrate_request_file(self, request_obj, file_field, file_type, progress):
        """Helper to migrate individual request files"""
        try:
            if not file_field or not hasattr(file_field, 'path'):
                return 'skipped'
            
            local_path = file_field.path
            
            if not os.path.exists(local_path):
                self.stdout.write(self.style.WARNING(
                    f'{progress} Request {request_obj.id}: {file_type} file not found'
                ))
                return 'skipped'
            
            self.stdout.write(f"{progress} Request {request_obj.id}: {file_field.name}")
            
            if self.dry_run:
                return 'skipped'
            
            with open(local_path, 'rb') as f:
                file_field.save(
                    file_field.name,
                    File(f),
                    save=False
                )
                request_obj.save()
            
            self.stdout.write(self.style.SUCCESS(f'  ✓ Uploaded {file_type} to B2'))
            return 'success'
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'{progress} ✗ Failed: {str(e)}'))
            return 'failed'
    
    def _format_size(self, bytes):
        """Format file size in human-readable format"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.1f} TB"
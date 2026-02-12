# datasets/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Browsing
    path('', views.dataset_list, name='dataset_list'),
    path('<int:pk>/', views.dataset_detail, name='dataset_detail'),
    path('<int:pk>/download/', views.dataset_download, name='dataset_download'),
    path('<int:pk>/rate/', views.rate_dataset, name='rate_dataset'),
    path('<int:pk>/save-to-collection/', views.save_to_collection, name='save_to_collection'),
    path('<int:pk>/report/', views.report_dataset, name='report_dataset'),
    path('<int:pk>/toggle-collection/', views.toggle_collection, name='toggle_collection'),
    path('my-requests/', views.my_requests, name='my_requests'),

    # Dataset requests
    path('<int:pk>/request/', views.dataset_request, name='dataset_request'),

    # Request status
    path('requests/<int:pk>/', views.request_status, name='request_status'),

    # Manager review
    path('review/<int:pk>/', views.manager_review_request, name='manager_review'),
    path('manager/review/', views.manager_review_list, name='manager_review_list'),

    # Director review
    path('director/review/<int:pk>/', views.director_review_request, name='director_review'),
    path('director/approvals/', views.director_approvals, name='director_approvals'),
    path('director/rejections/', views.director_rejections, name='director_rejections'),

    # Admin email functions
    path('admin/resend-notification/<int:pk>/', views.resend_notification, name='resend_notification'),
    path('preview-email/<int:pk>/', views.preview_acknowledgment_email, name='preview_acknowledgment_email'),
    # B2 Download URLs
    path('dataset/<int:pk>/download-b2/', 
         views.dataset_download_b2, 
         name='dataset_download_b2'),
    
    # API endpoint for AJAX downloads
    path('api/dataset/<int:pk>/download-url/', 
         views.get_dataset_download_url_api, 
         name='dataset_download_api'),
    
    # Preview and README URLs
    path('dataset/<int:pk>/preview/', 
         views.preview_dataset_file, 
         name='dataset_preview'),
    
    path('dataset/<int:pk>/readme/', 
         views.get_readme_url, 
         name='dataset_readme'),
    
    path('request/<int:pk>/document/<str:doc_type>/', 
     views.request_document_download, 
     name='request_document_download'),
]

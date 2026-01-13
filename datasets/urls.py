# datasets/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Dataset browsing and viewing
    path('', views.dataset_list, name='dataset_list'),
    path('<int:pk>/', views.dataset_detail, name='dataset_detail'),
    path('<int:pk>/download/', views.dataset_download, name='dataset_download'),
    path('<int:pk>/rate/', views.rate_dataset, name='rate_dataset'),
    path('<int:pk>/save-to-collection/', views.save_to_collection, name='save_to_collection'),
    path('<int:pk>/report/', views.report_dataset, name='report_dataset'),
    path('<int:pk>/toggle-collection/', views.toggle_collection, name='toggle_collection'),
    path('my-requests/', views.my_requests, name='my_requests'),
    # Dataset request workflow
    path('<int:pk>/request/', views.dataset_request, name='dataset_request'),
    path('requests/<int:pk>/', views.request_status, name='request_status'),
    path('download-request-form/', views.download_request_form, name='download_request_form'),

    # Email related URLs 
    path('request/<int:dataset_id>/', views.dataset_request, name='request_data'),
    path('request/status/<int:pk>/', views.request_status, name='request_status'),
    path('download/<int:dataset_id>/<int:pk>/', views.dataset_download, name='download_dataset'),

    # Manager review URLs - FOR DATA MANAGERS
    path('review/<int:pk>/', views.manager_review_request, name='manager_review'),  # CHANGED
    path('manager/review/<int:pk>/', views.manager_review_request, name='manager_review_detail'),  # ALTERNATIVE
    
    # Director review URLs - FOR DIRECTORS
    path('director/review/<int:pk>/', views.director_review_request, name='director_review'),  # CHANGED
    path('director/final-review/<int:pk>/', views.director_review_request, name='director_final_review'),  # ALTERNATIVE
    path('director/review/<int:request_id>/', views.director_review_request, name='director_review_request'),

    # Admin email functions
    path('admin/resend-notification/<int:pk>/', 
         views.resend_notification, 
         name='resend_notification'),
    path('preview-email/<int:pk>/', 
         views.preview_acknowledgment_email, 
         name='preview_acknowledgment_email'),
         
    # List views for managers and directors
    path('review/requests/', views.review_requests_list, name='review_requests_list'),
    path('manager/recommendations/', views.manager_recommendations, name='manager_recommendations'),
    path('manager/rejections/', views.manager_rejections, name='manager_rejections'),
    path('director/reviews/', views.director_review_list, name='director_review_list'),
    path('director/approvals/', views.director_approvals, name='director_approvals'),
    path('director/rejections/', views.director_rejections, name='director_rejections'),


    # Admin override URLs (for superusers)
    path('admin/requests/<int:pk>/review/', views.admin_review_request, name='admin_review_request'),
    path('admin/requests/<int:pk>/approve/', views.approve_request, name='approve_request'),
    path('reports/all-requests/', views.all_requests_report, name='all_requests_report'),

    path('test-email/', views.test_email_notification, name='test_email'),
]
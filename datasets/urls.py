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
    
    # Dataset request workflow
    path('<int:pk>/request/', views.dataset_request, name='dataset_request'),
    path('requests/<int:pk>/', views.request_status, name='request_status'),
    path('download-request-form/', views.download_request_form, name='download_request_form'),

    
    # Admin review URLs
    path('admin/requests/<int:pk>/review/', views.review_request, name='review_request'),
    path('admin/requests/<int:pk>/approve/', views.approve_request, name='approve_request'),
    path('request/review/<int:pk>/', views.review_request, name='review_request'),
    path('request/director-review/<int:pk>/', views.director_review, name='director_review'),
    path('manager/recommendations/', views.manager_recommendations, name='manager_recommendations'),
    path('manager/rejections/', views.manager_rejections, name='manager_rejections'),
    path('director/approvals/', views.director_approvals, name='director_approvals'),
    path('director/rejections/', views.director_rejections, name='director_rejections'),

]
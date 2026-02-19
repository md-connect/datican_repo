from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from datasets import views as dataset_views 
from datasets import views 


urlpatterns = [
    path('', include('core.urls')),

    # Dashboard URLs at root level
    path('manager/dashboard/', dataset_views.manager_dashboard, name='manager_dashboard'),
    path('director/dashboard/', dataset_views.director_dashboard, name='director_dashboard'),
    path('admin/dashboard/', dataset_views.admin_dashboard, name='admin_dashboard'),

    # Manager review URLs - FOR DATA MANAGERS
    path('review/<int:pk>/', views.manager_review_request, name='manager_review'),  # CHANGED
    path('manager/review/<int:pk>/', views.manager_review_request, name='manager_review_detail'),  # ALTERNATIVE
    
    # Director review URLs - FOR DIRECTORS
    path('director/review/<int:pk>/', views.director_review_request, name='director_review'),  # CHANGED
    path('director/final-review/<int:pk>/', views.director_review_request, name='director_final_review'),  # ALTERNATIVE
    path('director/review/<int:request_id>/', views.director_review_request, name='director_review_request'),

    # List views for managers and directors
    path('review/requests/', views.review_requests_list, name='review_requests_list'),
    path('manager/recommendations/', views.manager_recommendations, name='manager_recommendations'),
    path('manager/rejections/', views.manager_rejections, name='manager_rejections'),
    path('director/reviews/', views.director_review_list, name='director_review_list'),
    path('director/approvals/', views.director_approvals, name='director_approvals'),
    path('director/rejections/', views.director_rejections, name='director_rejections'),
    path('manager/director-decisions/', views.director_decisions_for_manager, name='director_decisions_manager'),
    # Admin override URLs (for superusers)
    path('admin/requests/<int:pk>/review/', views.admin_review_request, name='admin_review_request'),
    path('admin/all-requests/', views.admin_all_requests, name='admin_all_requests'),
    path('admin/requests/<int:pk>/approve/', views.approve_request, name='approve_request'),
    path('reports/all-requests/', views.all_requests_report, name='all_requests_report'),

    #path('datasets/', include(('datasets.urls', 'datasets'), namespace='datasets')),
    path('datasets/', include('datasets.urls')),
    path('accounts/', include('allauth.urls')),

    # Password reset URLs
    path(
        'admin/password_reset/',
        auth_views.PasswordResetView.as_view(),
        name='admin_password_reset',
    ),
    path(
        'admin/password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(),
        name='password_reset_complete',
    ),
    path('admin/', admin.site.urls),
    #path('accounts/', include('allauth.urls')), 

    path('redirect-after-login/', views.redirect_after_login, name='redirect_after_login'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

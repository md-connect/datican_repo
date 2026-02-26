from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
from core.views import CustomLoginView, CustomSignupView

urlpatterns = [
    path('', views.home, name='home'),

    path('login/', CustomLoginView.as_view(), name='login'),
    path('signup/', CustomSignupView.as_view(), name='signup'),
    
    # Override Allauth's default login/signup with our custom views
    path('accounts/login/', CustomLoginView.as_view(), name='account_login'),
    path('accounts/signup/', CustomSignupView.as_view(), name='account_signup'),
    # Specific first: email confirmation with key
    path('accounts/confirm-email/<str:key>/', views.CustomConfirmEmailView.as_view(),
         name='account_confirm_email'),

    # Base URL for "verification sent" page
    path('accounts/confirm-email/', views.CustomConfirmEmailView.as_view(),
         name='account_confirm_email_base'),

    path('auth/google/login/', views.google_login, name='google_login'),
    path('auth/google/callback/', views.google_callback, name='google_callback'),
     # Keep the rest of Allauth URLs
    
    path('profile/', views.profile_view, name='profile'),
    path('profile/password/', views.change_password, name='change_password'),
    path('logout/', LogoutView.as_view(next_page='/'), name='account_logout'),
    path('accounts/3rdparty/signup/', views.social_login_callback, name='social_callback'),
]
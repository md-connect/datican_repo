from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView


urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/password/', views.change_password, name='change_password'),
    #path('logout/', views.logout_view, name='logout'),
    path('logout/', LogoutView.as_view(next_page='/'), name='account_logout'),
    path('accounts/3rdparty/signup/', views.social_login_callback, name='social_callback'),
]
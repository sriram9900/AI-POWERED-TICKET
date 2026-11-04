
from django.contrib import admin
from django.urls import path, include
from accounts.views import home

urlpatterns = [
    path('', home, name='home'),

    path('admin/', admin.site.urls),

    path('api/auth/', include('accounts.urls')),
]

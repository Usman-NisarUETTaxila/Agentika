from django.urls import path
from .views import SearchQueryView

urlpatterns = [
    path('search/', SearchQueryView.as_view(), name='search-query'),
]
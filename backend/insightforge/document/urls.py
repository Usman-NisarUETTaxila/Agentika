from django.urls import path
from .views import DocumentListCreateView, DocumentDeleteView

urlpatterns = [
    path('documents/', DocumentListCreateView.as_view(), name='document-list-create'),
    path('documents/<int:pk>/', DocumentDeleteView.as_view(), name='document-delete'),
]

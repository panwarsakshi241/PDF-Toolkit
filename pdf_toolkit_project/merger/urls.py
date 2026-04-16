from django.urls import path
from . import views

urlpatterns = [
    path('',                views.index,         name='index'),
    path('merge/',          views.merge,         name='merge'),
    path('download/<int:job_id>/', views.download, name='download'),
    path('history/',        views.history,       name='history'),
    path('history/clear/',  views.clear_history, name='clear_history'),
]
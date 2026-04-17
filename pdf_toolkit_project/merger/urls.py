from django.urls import path
from . import views

urlpatterns = [
    path('',                       views.index,         name='index'),
    path('merge/',                 views.merge,         name='merge'),
    path('split/',                 views.split,         name='split'),
    path('extract/',               views.extract,       name='extract'),
    path('rotate/',                views.rotate,        name='rotate'),
    path('compress/',              views.compress,      name='compress'),
    path('download/<int:job_id>/', views.download,      name='download'),
    path('download-zip/<int:job_id>/', views.download_zip, name='download_zip'),
    path('history/',               views.history,       name='history'),
    path('history/clear/',         views.clear_history, name='clear_history'),
]
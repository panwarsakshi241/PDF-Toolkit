from django.contrib import admin
from .models import Job

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display   = ('tool', 'output_filename', 'total_pages', 'file_size_kb', 'created_at')
    list_filter    = ('tool',)
    readonly_fields = ('created_at',)
    search_fields  = ('output_filename', 'input_files')
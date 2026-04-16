from django.contrib import admin
from .models import MergeJob

@admin.register(MergeJob)
class MergeJobAdmin(admin.ModelAdmin):
    list_display  = ('output_filename', 'total_pages', 'file_size_kb', 'created_at')
    readonly_fields = ('created_at',)
    search_fields = ('output_filename', 'input_files')
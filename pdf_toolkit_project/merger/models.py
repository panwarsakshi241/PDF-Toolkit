from django.db import models

TOOL_CHOICES = [
    ('merge',    'Merge'),
    ('split',    'Split'),
    ('extract',  'Extract Pages'),
    ('rotate',   'Rotate'),
    ('compress', 'Compress'),
]

class Job(models.Model):
    """Unified history record for every tool operation."""
    tool            = models.CharField(max_length=20, choices=TOOL_CHOICES)
    output_filename = models.CharField(max_length=255)
    input_files     = models.TextField()          # comma-separated original names
    total_pages     = models.PositiveIntegerField(default=0)
    file_size_kb    = models.FloatField(default=0)
    output_path     = models.CharField(max_length=500)
    extra_info      = models.CharField(max_length=255, blank=True)  # e.g. "pages 5-10", "90°"
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.tool}] {self.output_filename} ({self.created_at:%Y-%m-%d %H:%M})"

    def input_files_list(self):
        return [f.strip() for f in self.input_files.split(',') if f.strip()]
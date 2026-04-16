from django.db import models


class MergeJob(models.Model):
    """Stores a record of every successful merge operation."""
    output_filename = models.CharField(max_length=255)
    input_files     = models.TextField()          # comma-separated original names
    total_pages     = models.PositiveIntegerField()
    file_size_kb    = models.FloatField()
    output_path     = models.CharField(max_length=500)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.output_filename} ({self.created_at:%Y-%m-%d %H:%M})"

    def input_files_list(self):
        return [f.strip() for f in self.input_files.split(',') if f.strip()]
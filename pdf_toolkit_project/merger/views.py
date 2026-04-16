import os
import uuid
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone

from PyPDF2 import PdfReader, PdfWriter

from .models import MergeJob


# ── Index ─────────────────────────────────────────────────────────────────────

def index(request):
    return render(request, 'merger/index.html')


# ── Merge ─────────────────────────────────────────────────────────────────────

@require_POST
def merge(request):
    files       = request.FILES.getlist('pdfs')          # uploaded file objects
    order_raw   = request.POST.get('order', '')          # e.g. "2,0,1"
    output_name = request.POST.get('output_name', '').strip() or 'merged'

    # Sanitise output filename
    output_name = "".join(c for c in output_name if c.isalnum() or c in '-_')
    if not output_name:
        output_name = 'merged'

    if not files:
        return JsonResponse({'error': 'No PDF files were uploaded.'}, status=400)

    # Re-order files if the client sent an order list
    if order_raw:
        try:
            indices = [int(i) for i in order_raw.split(',')]
            if sorted(indices) == list(range(len(files))):
                files = [files[i] for i in indices]
        except (ValueError, IndexError):
            pass  # fall back to original order

    writer      = PdfWriter()
    total_pages = 0
    names       = []
    errors      = []

    for f in files:
        if not f.name.lower().endswith('.pdf'):
            errors.append(f"{f.name} is not a PDF and was skipped.")
            continue
        try:
            reader = PdfReader(f)
            for page in reader.pages:
                writer.add_page(page)
            total_pages += len(reader.pages)
            names.append(f.name)
        except Exception as exc:
            errors.append(f"Could not read {f.name}: {exc}")

    if total_pages == 0:
        return JsonResponse({'error': 'No pages could be extracted. ' + ' '.join(errors)}, status=400)

    # Save to MEDIA_ROOT/merged/
    out_dir = Path(settings.MEDIA_ROOT) / 'merged'
    out_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{output_name}_{uuid.uuid4().hex[:8]}.pdf"
    out_path    = out_dir / unique_name

    with open(out_path, 'wb') as fh:
        writer.write(fh)

    size_kb = out_path.stat().st_size / 1024

    # Persist history record
    job = MergeJob.objects.create(
        output_filename = unique_name,
        input_files     = ', '.join(names),
        total_pages     = total_pages,
        file_size_kb    = round(size_kb, 1),
        output_path     = str(out_path),
    )

    return JsonResponse({
        'success'  : True,
        'job_id'   : job.pk,
        'filename' : unique_name,
        'pages'    : total_pages,
        'size_kb'  : round(size_kb, 1),
        'warnings' : errors,
        'download_url': f'/download/{job.pk}/',
    })


# ── Download ──────────────────────────────────────────────────────────────────

def download(request, job_id):
    try:
        job = MergeJob.objects.get(pk=job_id)
    except MergeJob.DoesNotExist:
        raise Http404("Merge job not found.")

    path = Path(job.output_path)
    if not path.exists():
        raise Http404("Merged file no longer exists on disk.")

    return FileResponse(
        open(path, 'rb'),
        as_attachment=True,
        filename=job.output_filename,
        content_type='application/pdf',
    )


# ── History ───────────────────────────────────────────────────────────────────

def history(request):
    jobs = MergeJob.objects.all()[:50]
    return render(request, 'merger/history.html', {'jobs': jobs})


@require_POST
def clear_history(request):
    # Delete DB records; also remove files from disk
    for job in MergeJob.objects.all():
        try:
            Path(job.output_path).unlink(missing_ok=True)
        except Exception:
            pass
    MergeJob.objects.all().delete()
    return redirect('history')
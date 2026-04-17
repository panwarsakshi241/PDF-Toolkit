import io
import os
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from PyPDF2 import PdfReader, PdfWriter

from .models import Job


# ── Helpers ───────────────────────────────────────────────────────────────────

def _out_dir():
    d = Path(settings.MEDIA_ROOT) / 'jobs'
    d.mkdir(parents=True, exist_ok=True)
    return d

def _save_file(writer, stem, ext='pdf'):
    name = f"{stem}_{uuid.uuid4().hex[:8]}.{ext}"
    path = _out_dir() / name
    with open(path, 'wb') as fh:
        writer.write(fh)
    return path, name

def _save_zip(buf, stem):
    name = f"{stem}_{uuid.uuid4().hex[:8]}.zip"
    path = _out_dir() / name
    path.write_bytes(buf.getvalue())
    return path, name

def _record(tool, path, name, input_names, pages, extra=''):
    size_kb = round(path.stat().st_size / 1024, 1)
    return Job.objects.create(
        tool=tool, output_filename=name,
        input_files=', '.join(input_names),
        total_pages=pages, file_size_kb=size_kb,
        output_path=str(path), extra_info=extra,
    )

def _parse_pdf(upload):
    """Return a PdfReader or raise ValueError with a friendly message."""
    if not upload.name.lower().endswith('.pdf'):
        raise ValueError(f"{upload.name} is not a PDF.")
    return PdfReader(upload)

def _reorder(files, order_raw):
    if not order_raw:
        return files
    try:
        idx = [int(i) for i in order_raw.split(',')]
        if sorted(idx) == list(range(len(files))):
            return [files[i] for i in idx]
    except (ValueError, IndexError):
        pass
    return files


# ── Index ─────────────────────────────────────────────────────────────────────

def index(request):
    return render(request, 'merger/index.html')


# ── Merge ─────────────────────────────────────────────────────────────────────

@require_POST
def merge(request):
    files     = request.FILES.getlist('pdfs')
    files     = _reorder(files, request.POST.get('order', ''))
    out_stem  = _clean(request.POST.get('output_name', 'merged'))

    if not files:
        return JsonResponse({'error': 'No PDF files uploaded.'}, status=400)

    writer, pages, names, warns = PdfWriter(), 0, [], []
    for f in files:
        try:
            r = _parse_pdf(f)
            for p in r.pages: writer.add_page(p)
            pages += len(r.pages); names.append(f.name)
        except Exception as e:
            warns.append(str(e))

    if pages == 0:
        return JsonResponse({'error': 'No pages extracted. ' + ' '.join(warns)}, status=400)

    path, name = _save_file(writer, out_stem)
    job = _record('merge', path, name, names, pages)
    return JsonResponse({'success': True, 'job_id': job.pk, 'filename': name,
                         'pages': pages, 'size_kb': job.file_size_kb,
                         'warnings': warns, 'download_url': f'/download/{job.pk}/'})


# ── Split ─────────────────────────────────────────────────────────────────────

@require_POST
def split(request):
    upload = request.FILES.get('pdf')
    if not upload:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)
    try:
        reader = _parse_pdf(upload)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    n     = len(reader.pages)
    stem  = Path(upload.name).stem
    buf   = io.BytesIO()

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(reader.pages, 1):
            w = PdfWriter(); w.add_page(page)
            pb = io.BytesIO(); w.write(pb)
            zf.writestr(f"{stem}_page_{i:03d}.pdf", pb.getvalue())

    path, name = _save_zip(buf, f"{stem}_split")
    job = _record('split', path, name, [upload.name], n, extra=f'{n} pages → individual files')
    return JsonResponse({'success': True, 'job_id': job.pk, 'filename': name,
                         'pages': n, 'size_kb': job.file_size_kb,
                         'download_url': f'/download-zip/{job.pk}/'})


# ── Extract ───────────────────────────────────────────────────────────────────

@require_POST
def extract(request):
    upload  = request.FILES.get('pdf')
    p_from  = request.POST.get('page_from', '').strip()
    p_to    = request.POST.get('page_to',   '').strip()
    out_stem = _clean(request.POST.get('output_name', 'extracted'))

    if not upload:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)
    try:
        reader = _parse_pdf(upload)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    total = len(reader.pages)
    try:
        frm = max(1, int(p_from)) if p_from else 1
        to  = min(total, int(p_to)) if p_to else total
        if frm > to:
            raise ValueError
    except ValueError:
        return JsonResponse({'error': f'Invalid page range. PDF has {total} pages.'}, status=400)

    writer = PdfWriter()
    for i in range(frm - 1, to):
        writer.add_page(reader.pages[i])

    extracted = to - frm + 1
    path, name = _save_file(writer, out_stem)
    job = _record('extract', path, name, [upload.name], extracted,
                  extra=f'pages {frm}–{to} of {total}')
    return JsonResponse({'success': True, 'job_id': job.pk, 'filename': name,
                         'pages': extracted, 'size_kb': job.file_size_kb,
                         'extra': job.extra_info,
                         'download_url': f'/download/{job.pk}/'})


# ── Rotate ────────────────────────────────────────────────────────────────────

@require_POST
def rotate(request):
    upload   = request.FILES.get('pdf')
    degrees  = request.POST.get('degrees', '90')
    scope    = request.POST.get('scope', 'all')     # 'all' or 'range'
    p_from   = request.POST.get('page_from', '').strip()
    p_to     = request.POST.get('page_to',   '').strip()
    out_stem = _clean(request.POST.get('output_name', 'rotated'))

    if not upload:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)
    try:
        deg = int(degrees)
        assert deg in (90, 180, 270)
    except (ValueError, AssertionError):
        return JsonResponse({'error': 'Rotation must be 90, 180, or 270.'}, status=400)
    try:
        reader = _parse_pdf(upload)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    total  = len(reader.pages)
    writer = PdfWriter()

    if scope == 'range':
        try:
            frm = max(1, int(p_from)) if p_from else 1
            to  = min(total, int(p_to)) if p_to else total
        except ValueError:
            return JsonResponse({'error': 'Invalid page range.'}, status=400)
        rotate_set = set(range(frm - 1, to))
    else:
        rotate_set = set(range(total))

    for i, page in enumerate(reader.pages):
        if i in rotate_set:
            page.rotate(deg)
        writer.add_page(page)

    path, name = _save_file(writer, out_stem)
    info = f'all pages {deg}°' if scope == 'all' else f'pages {frm}–{to} rotated {deg}°'
    job  = _record('rotate', path, name, [upload.name], total, extra=info)
    return JsonResponse({'success': True, 'job_id': job.pk, 'filename': name,
                         'pages': total, 'size_kb': job.file_size_kb,
                         'extra': job.extra_info,
                         'download_url': f'/download/{job.pk}/'})


# ── Compress ──────────────────────────────────────────────────────────────────

@require_POST
def compress(request):
    upload   = request.FILES.get('pdf')
    out_stem = _clean(request.POST.get('output_name', 'compressed'))

    if not upload:
        return JsonResponse({'error': 'No file uploaded.'}, status=400)
    try:
        reader = _parse_pdf(upload)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    orig_kb = round(upload.size / 1024, 1)
    writer  = PdfWriter()
    for page in reader.pages:
        page.compress_content_streams()   # deflate page content streams
        writer.add_page(page)

    path, name = _save_file(writer, out_stem)
    new_kb  = round(path.stat().st_size / 1024, 1)
    saving  = round(100 * (1 - new_kb / orig_kb), 1) if orig_kb else 0
    job     = _record('compress', path, name, [upload.name],
                      len(reader.pages), extra=f'{orig_kb} KB → {new_kb} KB ({saving}% saved)')
    return JsonResponse({'success': True, 'job_id': job.pk, 'filename': name,
                         'pages': len(reader.pages), 'size_kb': new_kb,
                         'orig_kb': orig_kb, 'saving': saving,
                         'extra': job.extra_info,
                         'download_url': f'/download/{job.pk}/'})


# ── Download ──────────────────────────────────────────────────────────────────

def download(request, job_id):
    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        raise Http404("Job not found.")
    path = Path(job.output_path)
    if not path.exists():
        raise Http404("File no longer exists on disk.")
    return FileResponse(open(path, 'rb'), as_attachment=True,
                        filename=job.output_filename, content_type='application/pdf')

def download_zip(request, job_id):
    try:
        job = Job.objects.get(pk=job_id)
    except Job.DoesNotExist:
        raise Http404("Job not found.")
    path = Path(job.output_path)
    if not path.exists():
        raise Http404("File no longer exists on disk.")
    return FileResponse(open(path, 'rb'), as_attachment=True,
                        filename=job.output_filename, content_type='application/zip')


# ── History ───────────────────────────────────────────────────────────────────

def history(request):
    tool = request.GET.get('tool', '')
    jobs = Job.objects.all()
    if tool:
        jobs = jobs.filter(tool=tool)
    jobs = jobs[:100]
    return render(request, 'merger/history.html', {'jobs': jobs, 'active_tool': tool})

@require_POST
def clear_history(request):
    for job in Job.objects.all():
        try: Path(job.output_path).unlink(missing_ok=True)
        except Exception: pass
    Job.objects.all().delete()
    return redirect('history')


# ── Utils ─────────────────────────────────────────────────────────────────────

def _clean(name):
    name = "".join(c for c in name if c.isalnum() or c in '-_')
    return name or 'output'